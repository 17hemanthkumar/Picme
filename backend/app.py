# app.py  (Neon + deployment ready)
from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, request, jsonify, send_from_directory,
    render_template, session, redirect, url_for
)
from functools import wraps
import os
print("DATABASE_URL =", os.environ.get("DATABASE_URL"))
import base64
import numpy as np
import cv2
import face_recognition
import shutil
import threading
import json
import qrcode
from io import BytesIO
import uuid
from datetime import datetime

# DB: use Neon PostgreSQL
import psycopg2
import psycopg2.extras

# Face model
from face_model import FaceRecognitionModel
from face_utils import aggregate_face_encoding_from_bgr_frames, verify_liveness_from_bgr_frames


# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder='../frontend/static',
    template_folder='../frontend/pages'
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your_super_secret_key_here")

# Neon connection string (set this in Render/Railway/locally)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"
)

UPLOAD_FOLDER = os.path.join(BASE_DIR, '..', 'uploads')
PROCESSED_FOLDER = os.path.join(BASE_DIR, '..', 'processed')
EVENTS_DATA_PATH = os.path.join(BASE_DIR, '..', 'events_data.json')
KNOWN_FACES_DATA_PATH = os.path.join(BASE_DIR, 'known_faces.dat')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)


# --- DISABLE CACHING FOR ALL RESPONSES ---
@app.after_request
def add_no_cache_headers(response):
    """Disable caching for all responses to prevent stale content"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# --- INITIALIZE THE ML MODEL ---
model = FaceRecognitionModel(data_file=KNOWN_FACES_DATA_PATH)


# --- DB HELPER ---
def get_db_connection():
    """
    Connect to Neon PostgreSQL using DATABASE_URL.
    """
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as err:
        print(f"DB Error: {err}")
        return None


# --- AUTH GUARD ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('serve_login_page'))
        return f(*args, **kwargs)
    return decorated_function


# --- IMAGE PROCESSING / FACE LEARNING ---
def process_images(event_id):
    """
    For each uploaded image:
    - Detect all faces
    - Learn / update identities in the model
    - Classify image as individual / group and copy into processed folder
    """
    try:
        input_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
        output_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
        os.makedirs(output_dir, exist_ok=True)

        print(f"--- [PROCESS] Starting for event: {event_id} ---")

        for filename in os.listdir(input_dir):
            if (filename.lower().endswith(('.png', '.jpg', '.jpeg'))
                    and not filename.endswith('_qr.png')):

                image_path = os.path.join(input_dir, filename)
                print(f"--- [PROCESS] Image: {filename}")

                try:
                    image = face_recognition.load_image_file(image_path)
                    face_encodings = face_recognition.face_encodings(image)
                    print(f"--- [PROCESS] Found {len(face_encodings)} face(s) in {filename}")

                    # Learn / update all faces in this photo
                    person_ids_in_image = set()
                    for encoding in face_encodings:
                        person_id = model.learn_face(encoding)
                        if person_id:
                            person_ids_in_image.add(person_id)

                    # Organize photos into individual / group per person
                    if face_encodings:
                        for pid in person_ids_in_image:
                            person_dir = os.path.join(output_dir, pid)
                            indiv_dir = os.path.join(person_dir, "individual")
                            group_dir = os.path.join(person_dir, "group")
                            os.makedirs(indiv_dir, exist_ok=True)
                            os.makedirs(group_dir, exist_ok=True)

                            if len(face_encodings) == 1:
                                # Individual photo
                                shutil.copy(
                                    image_path,
                                    os.path.join(indiv_dir, filename)
                                )
                            else:
                                # Group photo (add watermarked_ prefix)
                                shutil.copy(
                                    image_path,
                                    os.path.join(group_dir, f"watermarked_{filename}")
                                )

                except Exception as e:
                    print(f"  -> ERROR processing {filename}: {e}")

        print(f"--- [PROCESS] Finished for event: {event_id} ---")

    except Exception as e:
        print(f"  -> FATAL ERROR during processing for event {event_id}: {e}")


# --- PAGE ROUTES ---
@app.route('/')
def serve_index():
    return render_template('index.html')


@app.route('/login')
def serve_login_page():
    return render_template('login.html')


@app.route('/signup')
def serve_signup_page():
    return render_template('signup.html')


@app.route('/homepage')
@login_required
def serve_homepage():
    import time
    return render_template('homepage.html', cache_bust=int(time.time()))


@app.route('/event_discovery')
@login_required
def serve_event_discovery():
    return render_template('event_discovery.html')


@app.route('/event_detail')
@login_required
def serve_event_detail():
    return render_template('event_detail.html')


@app.route('/biometric_authentication_portal')
@login_required
def serve_biometric_authentication_portal():
    return render_template('biometric_authentication_portal.html')


@app.route('/personal_photo_gallery')
@login_required
def serve_personal_photo_gallery():
    return render_template('personal_photo_gallery.html')


@app.route('/event_organizer')
def serve_event_organizer():
    # Allow access for admins or logged-in users (organizers)
    if not session.get('admin_logged_in') and not session.get('logged_in'):
        return redirect(url_for('serve_index'))
    return render_template('event_organizer.html')


# --- AUTH API ROUTES ---
@app.route('/register', methods=['POST'])
def register_user():
    data = request.get_json()
    full_name = data.get('fullName')
    email = data.get('email')
    password = data.get('password')
    user_type = data.get('userType', 'user')

    if not all([full_name, email, password]):
        return jsonify({"success": False, "error": "All fields are required"}), 400

    from werkzeug.security import generate_password_hash
    hashed_password = generate_password_hash(password)

    conn = get_db_connection()
    if conn is None:
        return jsonify({"success": False, "error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Check for existing email
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"success": False, "error": "Email already registered"}), 409

        cursor.execute(
            """
            INSERT INTO users (full_name, email, password, user_type)
            VALUES (%s, %s, %s, %s)
            """,
            (full_name, email, hashed_password, user_type)
        )
        conn.commit()
        return jsonify({"success": True, "message": "Registration successful!"}), 201

    except Exception as err:
        print(f"Registration error: {err}")
        conn.rollback()
        return jsonify({"success": False, "error": "Registration failed"}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/login', methods=['POST'])
def login_user():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not all([email, password]):
        return jsonify({"success": False, "error": "Email and password are required"}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"success": False, "error": "Database connection failed"}), 500

    from werkzeug.security import check_password_hash

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            "SELECT id, email, password, user_type FROM users WHERE email = %s",
            (email,)
        )
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            session['user_type'] = user.get('user_type', 'user')

            redirect_url = '/event_organizer' if session['user_type'] == 'organizer' else '/homepage'
            return jsonify({
                "success": True,
                "message": "Login successful!",
                "redirect": redirect_url
            }), 200
        else:
            return jsonify({"success": False, "error": "Invalid email or password"}), 401

    except Exception as err:
        print(f"Error during login: {err}")
        return jsonify({
            "success": False,
            "error": "An internal server error occurred during login."
        }), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/logout')
def logout_user():
    session.clear()
    return redirect(url_for('serve_index'))


# --- ADMIN AUTH ROUTES ---
@app.route('/admin/register', methods=['POST'])
def admin_register():
    data = request.get_json()
    organization_name = data.get('organizationName')
    email = data.get('email')
    password = data.get('password')

    if not organization_name or not email or not password:
        return jsonify({"success": False, "error": "All fields are required"}), 400

    from werkzeug.security import generate_password_hash
    hashed_password = generate_password_hash(password)

    conn = get_db_connection()
    if conn is None:
        return jsonify({"success": False, "error": "Database connection failed"}), 500

    try:
        cursor = conn.cursor()

        # Check if admin email already exists
        cursor.execute("SELECT id FROM admins WHERE email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Admin email already registered"}), 400

        # Insert new admin into admins table
        cursor.execute(
            """
            INSERT INTO admins (organization_name, email, password)
            VALUES (%s, %s, %s)
            """,
            (organization_name, email, hashed_password)
        )
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "message": "Admin account created successfully"})

    except Exception as e:
        print(f"Error during admin registration: {e}")
        if conn:
            conn.close()
        return jsonify({"success": False, "error": "Registration failed"}), 500


@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required"}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 500

    from werkzeug.security import check_password_hash

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT * FROM admins WHERE email = %s", (email,))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()

        if admin and check_password_hash(admin['password'], password):
            # Create admin session
            session['admin_logged_in'] = True
            session['admin_id'] = admin['id']
            session['admin_email'] = admin['email']
            session['admin_organization'] = admin['organization_name']

            return jsonify({
                "success": True,
                "message": "Admin login successful",
                "redirect": "/event_organizer"
            })
        else:
            return jsonify({"success": False, "message": "Invalid credentials"}), 401

    except Exception as e:
        print(f"Error during admin login: {e}")
        if conn:
            conn.close()
        return jsonify({"success": False, "message": "Login failed"}), 500


@app.route('/admin/logout')
def admin_logout():
    # Clear only admin session keys, preserve user session if exists
    session.pop('admin_logged_in', None)
    session.pop('admin_id', None)
    session.pop('admin_email', None)
    session.pop('admin_organization', None)
    return redirect(url_for('serve_index'))


# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('serve_index'))
        return f(*args, **kwargs)
    return decorated_function


# --- EVENTS API / PUBLIC DATA ---
@app.route('/events', methods=['GET'])
def get_events():
    try:
        if os.path.exists(EVENTS_DATA_PATH):
            with open(EVENTS_DATA_PATH, 'r') as f:
                events_data = json.load(f)
        else:
            events_data = []
        return jsonify(events_data)
    except Exception as e:
        print(f"Error loading events: {e}")
        return jsonify([])


# --- FACE RECOGNITION ---
@app.route('/recognize', methods=['POST'])
@login_required
def recognize_face():
    """
    Recognize face from either:
      - legacy: { "image": "<base64>" }
      - new:    { "images": ["<b64_1>", "<b64_2>", ...], "challenge_type": "BLINK"|"HEAD_TURN"|None }

    Multi-frame path aggregates multiple frames using quality scores,
    and applies liveness + anti-spoof checks before identification.
    """
    try:
        data = request.get_json() or {}
        event_id = data.get('event_id', 'default_event')

        frames_b64 = data.get('images')  # NEW: list of frames
        single_b64 = data.get('image')   # OLD: single frame
        challenge_type = data.get('challenge_type')

        if not frames_b64 and not single_b64:
            return jsonify({"success": False, "error": "No image provided"}), 400

        # --- Multi-frame path (preferred) ---
        if isinstance(frames_b64, list) and len(frames_b64) > 0:
            frames_bgr = []
            for b64_str in frames_b64:
                try:
                    img_bytes = base64.b64decode(b64_str)
                    np_arr = np.frombuffer(img_bytes, np.uint8)
                    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        frames_bgr.append(frame)
                except Exception as e:
                    print(f"[RECOGNIZE] Failed to decode one frame: {e}")

            if not frames_bgr:
                return jsonify({
                    "success": False,
                    "error": "Could not decode any webcam frames."
                }), 400

            # --- LIVENESS / SPOOF CHECK BEFORE MATCHING ---
            is_live, debug_info = verify_liveness_from_bgr_frames(frames_bgr, challenge_type)
            print(f"[LIVENESS DEBUG] {debug_info}")
            if not is_live:
                return jsonify({
                    "success": False,
                    "error": "Liveness check failed. Please follow the on-screen challenge with your real face (no photos or screens)."
                }), 403

            # If live → build robust encoding
            scanned_encoding = aggregate_face_encoding_from_bgr_frames(frames_bgr)
            if scanned_encoding is None:
                return jsonify({
                    "success": False,
                    "error": "No clear face detected in captured frames."
                }), 400

        # --- Legacy single-frame path (still supported, no liveness) ---
        else:
            img_bytes = base64.b64decode(single_b64)
            np_arr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if img is None:
                return jsonify({
                    "success": False,
                    "error": "Unable to decode image."
                }), 400

            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_img)
            if not face_locations:
                return jsonify({
                    "success": False,
                    "error": "No face detected in scan."
                }), 400

            scanned_encoding = face_recognition.face_encodings(
                rgb_img, face_locations
            )[0]

        # --- Use ML model for identification ---
        person_id = model.recognize_face(scanned_encoding)

        if not person_id:
            return jsonify({
                "success": False,
                "error": "No confident match found."
            }), 404

        # Reinforce identity with this new high-quality encoding
        try:
            idx = model.known_ids.index(person_id)
            model.update_person_encoding(idx, scanned_encoding)
        except ValueError:
            # If for some reason ID isn't in list, just ignore
            pass

        # Locate this person's photos for the requested event
        person_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id, person_id)
        if not os.path.exists(person_dir):
            return jsonify({
                "success": False,
                "error": "Match found, but no photos in this event."
            }), 404

        individual_dir = os.path.join(person_dir, "individual")
        group_dir = os.path.join(person_dir, "group")

        individual_photos = (
            [f for f in os.listdir(individual_dir)]
            if os.path.exists(individual_dir) else []
        )
        group_photos = (
            [f for f in os.listdir(group_dir) if f.startswith('watermarked_')]
            if os.path.exists(group_dir) else []
        )

        return jsonify({
            "success": True,
            "person_id": person_id,
            "individual_photos": individual_photos,
            "group_photos": group_photos,
            "event_id": event_id
        })

    except Exception as e:
        print(f"[RECOGNIZE ERROR]: {e}")
        return jsonify({
            "success": False,
            "error": "An internal error occurred."
        }), 500


# --- EVENT ORGANIZER API ---
@app.route('/api/create_event', methods=['POST'])
def create_event():
    # Allow access for admins or logged-in users
    if not session.get('admin_logged_in') and not session.get('logged_in'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        data = request.get_json()
        event_name = data.get('eventName')
        event_location = data.get('eventLocation')
        event_date = data.get('eventDate')
        event_category = data.get('eventCategory', 'General')

        if not all([event_name, event_location, event_date]):
            return jsonify({"success": False, "error": "All fields are required"}), 400

        event_id = f"event_{uuid.uuid4().hex[:8]}"

        # Folder structure
        event_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
        event_processed_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
        os.makedirs(event_upload_dir, exist_ok=True)
        os.makedirs(event_processed_dir, exist_ok=True)

        # QR code
        qr_data = f"{request.host_url.rstrip('/')}/event_detail?event_id={event_id}"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_path = os.path.join(event_upload_dir, f"{event_id}_qr.png")
        qr_img.save(qr_path)

        # events_data.json
        if os.path.exists(EVENTS_DATA_PATH):
            with open(EVENTS_DATA_PATH, 'r') as f:
                events_data = json.load(f)
        else:
            events_data = []

        # Determine who created the event (admin or regular user)
        created_by_admin_id = session.get('admin_id') if session.get('admin_logged_in') else None
        created_by_user_id = session.get('user_id') if not session.get('admin_logged_in') else None
        
        new_event = {
            "id": event_id,
            "name": event_name,
            "location": event_location,
            "date": event_date,
            "category": event_category,
            "image": "/static/images/default_event.jpg",
            "photos_count": 0,
            "qr_code": f"/api/qr_code/{event_id}",
            "created_by_admin_id": created_by_admin_id,
            "created_by_user_id": created_by_user_id,
            "created_at": datetime.now().isoformat(),
            "sample_photos": []
        }

        events_data.append(new_event)
        with open(EVENTS_DATA_PATH, 'w') as f:
            json.dump(events_data, f, indent=2)

        return jsonify({
            "success": True,
            "event_id": event_id,
            "message": "Event created successfully!"
        }), 201

    except Exception as e:
        print(f"Error creating event: {e}")
        return jsonify({"success": False, "error": "Failed to create event"}), 500


@app.route('/api/qr_code/<event_id>')
def get_qr_code(event_id):
    qr_path = os.path.join(app.config['UPLOAD_FOLDER'], event_id, f"{event_id}_qr.png")
    if os.path.exists(qr_path):
        return send_from_directory(
            os.path.join(app.config['UPLOAD_FOLDER'], event_id),
            f"{event_id}_qr.png"
        )
    return "QR Code not found", 404


@app.route('/api/upload_photos/<event_id>', methods=['POST'])
def upload_event_photos(event_id):
    # Allow access for admins or logged-in users
    if not session.get('admin_logged_in') and not session.get('logged_in'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        if 'photos' not in request.files:
            return jsonify({"success": False, "error": "No photos uploaded"}), 400

        files = request.files.getlist('photos')
        if not files or files[0].filename == '':
            return jsonify({"success": False, "error": "No photos selected"}), 400

        event_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
        if not os.path.exists(event_dir):
            return jsonify({"success": False, "error": "Event not found"}), 404

        uploaded_files = []
        for file in files:
            if file and file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
                file_path = os.path.join(event_dir, filename)
                file.save(file_path)
                uploaded_files.append(filename)

        # Process in background
        threading.Thread(target=process_images, args=(event_id,)).start()

        # Update photo count
        if os.path.exists(EVENTS_DATA_PATH):
            with open(EVENTS_DATA_PATH, 'r') as f:
                events_data = json.load(f)

            for event in events_data:
                if event['id'] == event_id:
                    event['photos_count'] += len(uploaded_files)
                    break

            with open(EVENTS_DATA_PATH, 'w') as f:
                json.dump(events_data, f, indent=2)

        return jsonify({
            "success": True,
            "message": f"Successfully uploaded {len(uploaded_files)} photos",
            "uploaded_files": uploaded_files
        }), 200

    except Exception as e:
        print(f"Error uploading photos: {e}")
        return jsonify({"success": False, "error": "Failed to upload photos"}), 500


@app.route('/api/my_events')
def get_my_events():
    # Allow access for admins or logged-in users
    if not session.get('admin_logged_in') and not session.get('logged_in'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        if os.path.exists(EVENTS_DATA_PATH):
            with open(EVENTS_DATA_PATH, 'r') as f:
                all_events = json.load(f)

            # Filter events based on who is logged in
            if session.get('admin_logged_in'):
                # Admin sees only their events
                admin_id = session.get('admin_id')
                user_events = [
                    event for event in all_events
                    if event.get('created_by_admin_id') == admin_id
                ]
            else:
                # Regular user sees only their events
                user_id = session.get('user_id')
                user_events = [
                    event for event in all_events
                    if event.get('created_by_user_id') == user_id
                ]
            
            return jsonify({"success": True, "events": user_events})

        return jsonify({"success": True, "events": []})

    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify({"success": False, "error": "Failed to fetch events"}), 500


# --- PUBLIC & PRIVATE PHOTO SERVING ---
@app.route('/api/events/<event_id>/photos', methods=['GET'])
def get_event_photos(event_id):
    # (simple version: no pagination, returns all group photos)
    event_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
    if not os.path.exists(event_dir):
        return jsonify({"success": False, "error": "No photos found for this event yet."}), 404

    unique_photos = set()
    for person_id in os.listdir(event_dir):
        group_dir = os.path.join(event_dir, person_id, "group")
        if os.path.exists(group_dir):
            for filename in os.listdir(group_dir):
                if filename.startswith('watermarked_'):
                    unique_photos.add(filename)

    photo_urls = [
        f"/photos/{event_id}/all/{filename}"
        for filename in sorted(list(unique_photos))
    ]
    # Frontend expects success + photos; you can add has_next if you later add pagination
    return jsonify({"success": True, "photos": photo_urls, "has_next": False})


@app.route('/photos/<event_id>/all/<filename>')
def get_public_photo(event_id, filename):
    event_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
    for person_id in os.listdir(event_dir):
        photo_path = os.path.join(event_dir, person_id, "group", filename)
        if os.path.exists(photo_path):
            return send_from_directory(
                os.path.join(event_dir, person_id, "group"),
                filename
            )
    return "File Not Found", 404


@app.route('/photos/<event_id>/<person_id>/<photo_type>/<filename>')
def get_private_photo(event_id, person_id, photo_type, filename):
    # Allow access for admins or logged-in users
    if not session.get('admin_logged_in') and not session.get('logged_in'):
        return "Unauthorized", 401

    photo_path = os.path.join(
        app.config['PROCESSED_FOLDER'],
        event_id,
        person_id,
        photo_type
    )
    return send_from_directory(photo_path, filename)


@app.route('/api/download_photos', methods=['POST'])
@login_required
def download_photos():
    """
    Download multiple photos as a ZIP file (for personal gallery)
    """
    try:
        import zipfile
        from flask import send_file
        
        data = request.get_json()
        event_id = data.get('event_id')
        person_id = data.get('person_id')
        photos = data.get('photos', [])

        if not all([event_id, person_id, photos]):
            return jsonify({"success": False, "error": "Missing required parameters"}), 400

        # Create a temporary ZIP file
        zip_filename = f"photos_{event_id}_{person_id}_{uuid.uuid4().hex[:8]}.zip"
        zip_path = os.path.join(app.config['PROCESSED_FOLDER'], zip_filename)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for photo in photos:
                filename = photo.get('filename')
                photo_type = photo.get('photoType')
                
                # Remove watermarked_ prefix if present for the actual file
                actual_filename = filename.replace('watermarked_', '') if filename.startswith('watermarked_') else filename
                
                photo_path = os.path.join(
                    app.config['PROCESSED_FOLDER'],
                    event_id,
                    person_id,
                    photo_type,
                    filename
                )

                if os.path.exists(photo_path):
                    # Add to ZIP with a clean filename
                    zipf.write(photo_path, arcname=actual_filename)

        # Send the ZIP file
        response = send_file(
            zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"picme_photos_{event_id}.zip"
        )

        # Schedule cleanup of the ZIP file after sending
        def cleanup_zip():
            import time
            time.sleep(5)  # Wait 5 seconds before cleanup
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                    print(f"Cleaned up temporary ZIP: {zip_path}")
            except Exception as e:
                print(f"Error cleaning up ZIP: {e}")

        threading.Thread(target=cleanup_zip).start()

        return response

    except Exception as e:
        print(f"Error creating ZIP download: {e}")
        return jsonify({"success": False, "error": "Failed to create download"}), 500


@app.route('/api/download_event_photos', methods=['POST'])
@login_required
def download_event_photos():
    """
    Download multiple event photos as a ZIP file (for event detail page)
    """
    try:
        import zipfile
        from flask import send_file
        
        data = request.get_json()
        event_id = data.get('event_id')
        photo_urls = data.get('photo_urls', [])

        if not all([event_id, photo_urls]):
            return jsonify({"success": False, "error": "Missing required parameters"}), 400

        # Create a temporary ZIP file
        zip_filename = f"event_photos_{event_id}_{uuid.uuid4().hex[:8]}.zip"
        zip_path = os.path.join(app.config['PROCESSED_FOLDER'], zip_filename)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for photo_url in photo_urls:
                # Parse the URL to get the file path
                # URL format: /photos/event_id/all/filename
                parts = photo_url.split('/')
                if len(parts) >= 4:
                    filename = parts[-1]
                    # Remove watermarked_ prefix for cleaner filenames
                    clean_filename = filename.replace('watermarked_', '')
                    
                    # Find the actual file in the processed folder
                    event_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
                    if os.path.exists(event_dir):
                        for person_id in os.listdir(event_dir):
                            group_dir = os.path.join(event_dir, person_id, "group")
                            photo_path = os.path.join(group_dir, filename)
                            if os.path.exists(photo_path):
                                # Add to ZIP with clean filename
                                zipf.write(photo_path, arcname=clean_filename)
                                break

        # Send the ZIP file
        response = send_file(
            zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"event_photos_{event_id}.zip"
        )

        # Schedule cleanup of the ZIP file after sending
        def cleanup_zip():
            import time
            time.sleep(5)  # Wait 5 seconds before cleanup
            try:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                    print(f"Cleaned up temporary ZIP: {zip_path}")
            except Exception as e:
                print(f"Error cleaning up ZIP: {e}")

        threading.Thread(target=cleanup_zip).start()

        return response

    except Exception as e:
        print(f"Error creating event photos ZIP download: {e}")
        return jsonify({"success": False, "error": "Failed to create download"}), 500


# --- ADMIN PHOTO ACCESS ROUTES ---
@app.route('/api/admin/events/<event_id>/all-photos', methods=['GET'])
def get_admin_all_photos(event_id):
    """Admin endpoint to get ORIGINAL uploaded photos for an event (no duplicates)"""
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "error": "Admin access required"}), 403

    # Get photos from uploads folder (original photos only)
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
    if not os.path.exists(upload_dir):
        return jsonify({"success": False, "error": "No photos found for this event yet."}), 404

    all_photos = []

    # Get all original uploaded photos
    for filename in os.listdir(upload_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')) and not filename.endswith('_qr.png'):
            all_photos.append({
                "url": f"/api/admin/photos/{event_id}/{filename}",
                "filename": filename,
                "original_filename": filename
            })

    return jsonify({
        "success": True,
        "photos": all_photos,
        "total": len(all_photos)
    })


@app.route('/api/admin/photos/<event_id>/<filename>')
def serve_admin_photo(event_id, filename):
    """Serve original uploaded photos to admin"""
    if not session.get('admin_logged_in'):
        return "Unauthorized", 403

    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
    if os.path.exists(os.path.join(upload_dir, filename)):
        return send_from_directory(upload_dir, filename)
    return "File Not Found", 404


@app.route('/api/admin/photos/delete', methods=['POST'])
def delete_photo():
    """Admin endpoint to delete a photo from uploads folder"""
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "error": "Admin access required"}), 403

    data = request.get_json()
    event_id = data.get('event_id')
    filename = data.get('filename')

    if not all([event_id, filename]):
        return jsonify({"success": False, "error": "Missing required parameters"}), 400

    # Delete from uploads folder
    upload_path = os.path.join(
        app.config['UPLOAD_FOLDER'],
        event_id,
        filename
    )

    try:
        # Delete the original uploaded photo
        if os.path.exists(upload_path):
            os.remove(upload_path)
            print(f"Deleted upload photo: {upload_path}")
        else:
            return jsonify({"success": False, "error": "Photo not found"}), 404

        # Update events_data.json photo count
        if os.path.exists(EVENTS_DATA_PATH):
            with open(EVENTS_DATA_PATH, 'r') as f:
                events_data = json.load(f)

            for event in events_data:
                if event['id'] == event_id and event.get('photos_count', 0) > 0:
                    event['photos_count'] -= 1
                    break

            with open(EVENTS_DATA_PATH, 'w') as f:
                json.dump(events_data, f, indent=2)

        return jsonify({
            "success": True,
            "message": "Photo deleted successfully. Run reprocessing to update face recognition."
        })

    except Exception as e:
        print(f"Error deleting photo: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to delete photo: {str(e)}"
        }), 500


# --- STARTUP TASKS ---
def process_existing_uploads_on_startup():
    print("--- [LOG] Checking for existing photos on startup... ---")
    if os.path.exists(UPLOAD_FOLDER):
        for event_id in os.listdir(UPLOAD_FOLDER):
            if os.path.isdir(os.path.join(UPLOAD_FOLDER, event_id)):
                threading.Thread(target=process_images, args=(event_id,)).start()


# --- ENTRY POINT ---
if __name__ == '__main__':
    if not os.path.exists(EVENTS_DATA_PATH):
        # You can also create an empty list file here if you want
        pass

    # Auto-generate known_faces.dat if it doesn't exist and there are photos to process
    if not os.path.exists(KNOWN_FACES_DATA_PATH):
        print("[LOG] known_faces.dat not found. Checking for photos to process...")
        has_photos = False
        if os.path.exists(UPLOAD_FOLDER):
            for event_id in os.listdir(UPLOAD_FOLDER):
                event_dir = os.path.join(UPLOAD_FOLDER, event_id)
                if os.path.isdir(event_dir):
                    photos = [f for f in os.listdir(event_dir) 
                             if f.lower().endswith(('.png', '.jpg', '.jpeg')) 
                             and not f.endswith('_qr.png')]
                    if photos:
                        has_photos = True
                        break
        
        if has_photos:
            print("[LOG] Photos found. Auto-generating face recognition model...")
            process_existing_uploads_on_startup()
            print("[LOG] Face recognition model generation started in background.")
        else:
            print("[LOG] No photos found. Face recognition model will be created when photos are uploaded.")
    else:
        print("[LOG] Face recognition model loaded successfully.")

    port = int(os.environ.get("PORT", 5000))
    # Use 127.0.0.1 for localhost only, or 0.0.0.0 for network access
    app.run(host='127.0.0.1', port=port, debug=True)
