# app.py  (Neon + deployment ready)
from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, request, jsonify, send_from_directory,
    render_template, session, redirect, url_for
)
from functools import wraps
import os
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
from backend.face_model import FaceRecognitionModel
from backend.face_utils import aggregate_face_encoding_from_bgr_frames, verify_liveness_from_bgr_frames


# --- CONFIGURATION ---
import logging

# Configure logging - use WARNING level for production performance
# Set to INFO only for debugging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "..", "frontend", "pages"),
    static_folder=os.path.join(BASE_DIR, "..", "frontend", "static"),
    static_url_path='/static'
)

# Environment variable configuration with logging
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
    logger.warning("FLASK_SECRET_KEY environment variable not set. Using default (not secure for production).")
    FLASK_SECRET_KEY = "your_super_secret_key_here"
app.secret_key = FLASK_SECRET_KEY

# Neon connection string (set this in Render/Railway/locally)
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    logger.warning("DATABASE_URL environment variable not set. Using default placeholder.")
    DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require"

# Port configuration
PORT = int(os.environ.get("PORT", 8080))
logger.info(f"Application will run on port: {PORT}")

# File paths - use relative paths from BASE_DIR
UPLOAD_FOLDER = os.path.join(BASE_DIR, '..', 'uploads')
PROCESSED_FOLDER = os.path.join(BASE_DIR, '..', 'processed')
EVENTS_DATA_PATH = os.path.join(BASE_DIR, '..', 'events_data.json')
KNOWN_FACES_DATA_PATH = os.path.join(BASE_DIR, 'known_faces.dat')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Directory initialization with error handling
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    logger.info(f"Upload folder ready: {UPLOAD_FOLDER}")
except Exception as e:
    logger.error(f"Failed to create upload folder: {e}")
    raise

try:
    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    logger.info(f"Processed folder ready: {PROCESSED_FOLDER}")
except Exception as e:
    logger.error(f"Failed to create processed folder: {e}")
    raise

# Initialize events_data.json if it doesn't exist
try:
    if not os.path.exists(EVENTS_DATA_PATH):
        with open(EVENTS_DATA_PATH, 'w') as f:
            json.dump([], f)
        logger.info(f"Created events_data.json at: {EVENTS_DATA_PATH}")
except Exception as e:
    logger.error(f"Failed to create events_data.json: {e}")
    raise


# --- DISABLE CACHING FOR ALL RESPONSES ---
@app.after_request
def add_cache_headers(response):
    """
    Optimize caching for better performance:
    - Static assets (CSS, JS, images): Cache for 1 hour
    - HTML pages: No cache (always fresh)
    - API responses: No cache (always fresh)
    """
    path = request.path
    
    # Cache static assets for better performance
    if path.startswith('/static/') or path.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.svg', '.ico')):
        response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour
    else:
        # No cache for HTML pages and API responses
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
        # Log error without exposing connection string details
        logger.error("Database connection failed")
        return None


# --- AUTH GUARD ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('serve_login_page'))
        return f(*args, **kwargs)
    return decorated_function


# --- SECURITY HELPERS ---
def sanitize_filename(filename):
    """
    Sanitize filename to prevent path traversal attacks.
    Removes directory separators and ensures filename is safe.
    """
    import re
    # Get just the basename (removes any path components)
    filename = os.path.basename(filename)
    # Remove any remaining path separators
    filename = filename.replace('/', '').replace('\\', '')
    # Remove any null bytes
    filename = filename.replace('\x00', '')
    # Remove leading dots to prevent hidden files
    filename = filename.lstrip('.')
    # Only allow alphanumeric, dash, underscore, and dot
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    return filename


def validate_file_upload(file, allowed_extensions=None, max_size_mb=10):
    """
    Validate uploaded file for security.
    
    Args:
        file: FileStorage object from Flask request
        allowed_extensions: Set of allowed file extensions (e.g., {'.png', '.jpg', '.jpeg'})
        max_size_mb: Maximum file size in megabytes
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not file or not file.filename:
        return False, "No file provided"
    
    # Check file extension
    if allowed_extensions:
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return False, f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
    
    # Check file size (read first chunk to verify it's not empty)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    if file_size == 0:
        return False, "File is empty"
    
    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size > max_size_bytes:
        return False, f"File too large. Maximum size: {max_size_mb}MB"
    
    return True, None


def sanitize_path_component(component):
    """
    Sanitize a path component (like event_id or person_id) to prevent path traversal.
    """
    # Remove any path separators
    component = str(component).replace('/', '').replace('\\', '')
    # Remove null bytes
    component = component.replace('\x00', '')
    # Remove parent directory references
    component = component.replace('..', '')
    return component


# --- IMAGE PROCESSING / FACE LEARNING ---
def process_images(event_id):
    """
    For each uploaded image:
    - Detect all faces
    - Learn / update identities in the model
    - Classify image as individual / group and copy into processed folder
    """
    try:
        # Sanitize event_id to prevent path traversal
        event_id = sanitize_path_component(event_id)
        
        input_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
        output_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"[PHOTO_PROCESSING] Output directory ready - event_id: {event_id}, path: {output_dir}, operation: process_images")
        except Exception as e:
            logger.error(f"[PHOTO_PROCESSING] Failed to create output directory - event_id: {event_id}, path: {output_dir}, error: {str(e)}, operation: process_images")
            return

        logger.info(f"[PHOTO_PROCESSING] Starting processing for event: {event_id}, input_dir: {input_dir}, output_dir: {output_dir}, operation: process_images")

        if not os.path.exists(input_dir):
            logger.error(f"[PHOTO_PROCESSING] Input directory not found - event_id: {event_id}, path: {input_dir}, operation: process_images")
            return

        photos_processed = 0
        photos_failed = 0
        total_faces_detected = 0

        for filename in os.listdir(input_dir):
            if (filename.lower().endswith(('.png', '.jpg', '.jpeg'))
                    and not filename.endswith('_qr.png')):

                image_path = os.path.join(input_dir, filename)
                logger.info(f"[PHOTO_PROCESSING] Processing image - event_id: {event_id}, filename: {filename}, path: {image_path}, operation: process_images")

                # Load image with error handling
                try:
                    logger.info(f"[PHOTO_PROCESSING] Loading image file - event_id: {event_id}, filename: {filename}, operation: load_image")
                    image = face_recognition.load_image_file(image_path)
                    logger.info(f"[PHOTO_PROCESSING] Image loaded successfully - event_id: {event_id}, filename: {filename}, shape: {image.shape}, operation: load_image")
                except Exception as e:
                    logger.error(f"[PHOTO_PROCESSING] Failed to load image - event_id: {event_id}, filename: {filename}, error: {str(e)}, operation: load_image")
                    photos_failed += 1
                    continue

                # Face detection with error handling
                try:
                    logger.info(f"[PHOTO_PROCESSING] Starting face detection - event_id: {event_id}, filename: {filename}, operation: face_detection")
                    face_encodings = face_recognition.face_encodings(image)
                    face_count = len(face_encodings)
                    total_faces_detected += face_count
                    logger.info(f"[PHOTO_PROCESSING] Face detection complete - event_id: {event_id}, filename: {filename}, faces_detected: {face_count}, operation: face_detection")
                except Exception as e:
                    logger.error(f"[PHOTO_PROCESSING] Face detection failed - event_id: {event_id}, filename: {filename}, error: {str(e)}, operation: face_detection")
                    photos_failed += 1
                    continue

                # Face learning with error handling
                person_ids_in_image = set()
                if face_encodings:
                    logger.info(f"[PHOTO_PROCESSING] Starting face learning - event_id: {event_id}, filename: {filename}, face_count: {face_count}, operation: face_learning")
                    for idx, encoding in enumerate(face_encodings):
                        try:
                            person_id = model.learn_face(encoding)
                            if person_id:
                                person_ids_in_image.add(person_id)
                                logger.info(f"[PHOTO_PROCESSING] Face learned - event_id: {event_id}, filename: {filename}, face_index: {idx}, person_id: {person_id}, operation: face_learning")
                            else:
                                logger.warning(f"[PHOTO_PROCESSING] Face learning returned no ID - event_id: {event_id}, filename: {filename}, face_index: {idx}, operation: face_learning")
                        except Exception as e:
                            logger.error(f"[PHOTO_PROCESSING] Face learning failed - event_id: {event_id}, filename: {filename}, face_index: {idx}, error: {str(e)}, operation: face_learning")
                            continue

                    logger.info(f"[PHOTO_PROCESSING] Face learning complete - event_id: {event_id}, filename: {filename}, person_ids: {list(person_ids_in_image)}, operation: face_learning")

                # Organize photos into individual / group per person
                if face_encodings and person_ids_in_image:
                    logger.info(f"[PHOTO_PROCESSING] Starting photo organization - event_id: {event_id}, filename: {filename}, person_count: {len(person_ids_in_image)}, operation: photo_organization")
                    
                    for pid in person_ids_in_image:
                        person_dir = os.path.join(output_dir, pid)
                        indiv_dir = os.path.join(person_dir, "individual")
                        group_dir = os.path.join(person_dir, "group")
                        
                        # Create directories with error handling
                        try:
                            os.makedirs(indiv_dir, exist_ok=True)
                            os.makedirs(group_dir, exist_ok=True)
                            logger.info(f"[PHOTO_PROCESSING] Directories created - event_id: {event_id}, person_id: {pid}, individual: {indiv_dir}, group: {group_dir}, operation: create_directories")
                        except Exception as e:
                            logger.error(f"[PHOTO_PROCESSING] Failed to create directories - event_id: {event_id}, person_id: {pid}, error: {str(e)}, operation: create_directories")
                            continue

                        # Copy file with error handling
                        try:
                            if len(face_encodings) == 1:
                                # Individual photo
                                dest_path = os.path.join(indiv_dir, filename)
                                logger.info(f"[PHOTO_PROCESSING] Copying individual photo - event_id: {event_id}, filename: {filename}, person_id: {pid}, source: {image_path}, dest: {dest_path}, operation: file_copy")
                                shutil.copy(image_path, dest_path)
                                logger.info(f"[PHOTO_PROCESSING] Individual photo copied successfully - event_id: {event_id}, filename: {filename}, person_id: {pid}, dest: {dest_path}, operation: file_copy")
                            else:
                                # Group photo (add watermarked_ prefix)
                                dest_filename = f"watermarked_{filename}"
                                dest_path = os.path.join(group_dir, dest_filename)
                                logger.info(f"[PHOTO_PROCESSING] Copying group photo - event_id: {event_id}, filename: {filename}, person_id: {pid}, source: {image_path}, dest: {dest_path}, operation: file_copy")
                                shutil.copy(image_path, dest_path)
                                logger.info(f"[PHOTO_PROCESSING] Group photo copied successfully - event_id: {event_id}, filename: {filename}, person_id: {pid}, dest: {dest_path}, operation: file_copy")
                        except Exception as e:
                            logger.error(f"[PHOTO_PROCESSING] File copy failed - event_id: {event_id}, filename: {filename}, person_id: {pid}, error: {str(e)}, operation: file_copy")
                            continue
                    
                    photos_processed += 1
                    logger.info(f"[PHOTO_PROCESSING] Photo organization complete - event_id: {event_id}, filename: {filename}, operation: photo_organization")
                elif not face_encodings:
                    logger.warning(f"[PHOTO_PROCESSING] No faces detected in photo - event_id: {event_id}, filename: {filename}, operation: process_images")
                    photos_failed += 1
                else:
                    logger.warning(f"[PHOTO_PROCESSING] No person IDs generated - event_id: {event_id}, filename: {filename}, operation: process_images")
                    photos_failed += 1

        logger.info(f"[PHOTO_PROCESSING] Processing complete - event_id: {event_id}, photos_processed: {photos_processed}, photos_failed: {photos_failed}, total_faces_detected: {total_faces_detected}, operation: process_images")

    except Exception as e:
        logger.error(f"[PHOTO_PROCESSING] Fatal error during processing - event_id: {event_id}, error: {str(e)}, operation: process_images")
        import traceback
        logger.error(f"[PHOTO_PROCESSING] Traceback: {traceback.format_exc()}")


# --- PAGE ROUTES ---
@app.route('/')
def serve_index():
    return render_template('index.html')


@app.route('/picme.jpeg')
def serve_logo():
    """Serve the PicMe logo image - redirects to SVG"""
    static_images_dir = os.path.join(BASE_DIR, '..', 'frontend', 'static', 'images')
    # Check if JPEG exists, otherwise serve SVG
    jpeg_path = os.path.join(static_images_dir, 'picme.jpeg')
    svg_path = os.path.join(static_images_dir, 'picme.svg')
    
    if os.path.exists(jpeg_path):
        return send_from_directory(static_images_dir, 'picme.jpeg')
    elif os.path.exists(svg_path):
        return send_from_directory(static_images_dir, 'picme.svg', mimetype='image/svg+xml')
    else:
        return "Logo not found", 404

@app.route('/picme.svg')
def serve_logo_svg():
    """Serve the PicMe logo SVG"""
    static_images_dir = os.path.join(BASE_DIR, '..', 'frontend', 'static', 'images')
    svg_path = os.path.join(static_images_dir, 'picme.svg')
    
    if os.path.exists(svg_path):
        return send_from_directory(static_images_dir, 'picme.svg', mimetype='image/svg+xml')
    else:
        return "Logo not found", 404


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


@app.route('/download_page')
@login_required
def serve_download_page():
    return render_template('download_page.html')


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
        logger.error("Registration error occurred")
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
        logger.error("Login error occurred")
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
        logger.error("Admin registration error occurred")
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
        logger.error("Admin login error occurred")
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


@app.route('/api/events', methods=['GET'])
def get_events_api():
    """API endpoint to get all events without filtering"""
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

        # Store person_id in session for future API calls
        session['person_id'] = person_id

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
        # Check if request has multipart form data (with thumbnail) or JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Multipart form data with optional thumbnail
            event_name = request.form.get('eventName')
            event_location = request.form.get('eventLocation')
            event_date = request.form.get('eventDate')
            event_category = request.form.get('eventCategory', 'General')
            thumbnail_file = request.files.get('thumbnail')
        else:
            # JSON data (legacy support)
            data = request.get_json()
            event_name = data.get('eventName')
            event_location = data.get('eventLocation')
            event_date = data.get('eventDate')
            event_category = data.get('eventCategory', 'General')
            thumbnail_file = None

        if not all([event_name, event_location, event_date]):
            return jsonify({"success": False, "error": "All fields are required"}), 400

        event_id = f"event_{uuid.uuid4().hex[:8]}"

        # Folder structure
        event_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
        event_processed_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
        os.makedirs(event_upload_dir, exist_ok=True)
        os.makedirs(event_processed_dir, exist_ok=True)

        # Handle thumbnail upload
        thumbnail_filename = None
        thumbnail_path = "/static/images/default_event.jpg"
        
        if thumbnail_file and thumbnail_file.filename:
            # Validate file upload
            allowed_extensions = {'.png', '.jpg', '.jpeg'}
            is_valid, error_msg = validate_file_upload(thumbnail_file, allowed_extensions, max_size_mb=5)
            
            if not is_valid:
                return jsonify({
                    "success": False, 
                    "error": error_msg
                }), 400
            
            # Sanitize and generate unique filename
            file_ext = os.path.splitext(thumbnail_file.filename)[1].lower()
            thumbnail_filename = f"thumbnail_{uuid.uuid4().hex[:8]}{file_ext}"
            thumbnail_file_path = os.path.join(event_upload_dir, thumbnail_filename)
            
            # Save thumbnail file
            thumbnail_file.save(thumbnail_file_path)
            
            # Update thumbnail path to use API endpoint
            thumbnail_path = f"/api/events/{event_id}/thumbnail"

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
            "image": thumbnail_path,
            "thumbnail_filename": thumbnail_filename,
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
        logger.error("Error creating event")
        return jsonify({"success": False, "error": "Failed to create event"}), 500


@app.route('/api/qr_code/<event_id>')
def get_qr_code(event_id):
    # Store original value for logging
    original_event_id = event_id
    
    logger.info(f"[PHOTO_SERVING] Request for QR code - event_id: {event_id}, operation: get_qr_code")
    
    # Sanitize event_id to prevent path traversal
    event_id = sanitize_path_component(event_id)
    
    # Log if sanitization changed the value (potential security violation)
    if event_id != original_event_id:
        logger.warning(f"[SECURITY] Path sanitization applied - original_event_id: {original_event_id}, sanitized_event_id: {event_id}, operation: get_qr_code")
    
    qr_path = os.path.join(app.config['UPLOAD_FOLDER'], event_id, f"{event_id}_qr.png")
    
    if os.path.exists(qr_path):
        try:
            logger.info(f"[PHOTO_SERVING] Successfully serving QR code - event_id: {event_id}, operation: get_qr_code")
            return send_from_directory(
                os.path.join(app.config['UPLOAD_FOLDER'], event_id),
                f"{event_id}_qr.png"
            )
        except Exception as e:
            logger.error(f"[PHOTO_SERVING] Error serving QR code - event_id: {event_id}, error: {str(e)}, operation: get_qr_code")
            return "Internal Server Error", 500
    
    logger.error(f"[PHOTO_SERVING] QR code not found - event_id: {event_id}, path: {qr_path}, operation: get_qr_code")
    return "QR Code not found", 404


@app.route('/api/events/<event_id>/thumbnail')
def get_event_thumbnail(event_id):
    """Serve event thumbnail"""
    # Store original value for logging
    original_event_id = event_id
    
    logger.info(f"[PHOTO_SERVING] Request for event thumbnail - event_id: {event_id}, operation: get_event_thumbnail")
    
    # Sanitize event_id to prevent path traversal
    event_id = sanitize_path_component(event_id)
    
    # Log if sanitization changed the value (potential security violation)
    if event_id != original_event_id:
        logger.warning(f"[SECURITY] Path sanitization applied - original_event_id: {original_event_id}, sanitized_event_id: {event_id}, operation: get_event_thumbnail")
    
    try:
        # Load events data to get thumbnail filename
        if os.path.exists(EVENTS_DATA_PATH):
            with open(EVENTS_DATA_PATH, 'r') as f:
                events_data = json.load(f)
            
            # Find the event
            event = next((e for e in events_data if e['id'] == event_id), None)
            if event and event.get('thumbnail_filename'):
                # Sanitize thumbnail filename
                thumbnail_filename = sanitize_filename(event['thumbnail_filename'])
                thumbnail_path = os.path.join(
                    app.config['UPLOAD_FOLDER'], 
                    event_id, 
                    thumbnail_filename
                )
                if os.path.exists(thumbnail_path):
                    logger.info(f"[PHOTO_SERVING] Successfully serving thumbnail - event_id: {event_id}, filename: {thumbnail_filename}, operation: get_event_thumbnail")
                    return send_from_directory(
                        os.path.join(app.config['UPLOAD_FOLDER'], event_id),
                        thumbnail_filename
                    )
                else:
                    logger.error(f"[PHOTO_SERVING] Thumbnail file not found - event_id: {event_id}, filename: {thumbnail_filename}, path: {thumbnail_path}, operation: get_event_thumbnail")
            else:
                logger.error(f"[PHOTO_SERVING] Event not found or no thumbnail - event_id: {event_id}, operation: get_event_thumbnail")
        else:
            logger.error(f"[PHOTO_SERVING] Events data file not found - path: {EVENTS_DATA_PATH}, operation: get_event_thumbnail")
    except Exception as e:
        logger.error(f"[PHOTO_SERVING] Error serving thumbnail - event_id: {event_id}, error: {str(e)}, operation: get_event_thumbnail")
        return "Internal Server Error", 500
    
    return "Thumbnail not found", 404


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
        allowed_extensions = {'.png', '.jpg', '.jpeg'}
        
        for file in files:
            if file and file.filename:
                # Validate each file
                is_valid, error_msg = validate_file_upload(file, allowed_extensions, max_size_mb=10)
                
                if not is_valid:
                    logger.warning(f"File upload validation failed: {error_msg}")
                    continue  # Skip invalid files but continue processing others
                
                # Sanitize filename and generate unique name
                safe_filename = sanitize_filename(file.filename)
                filename = f"{uuid.uuid4().hex[:8]}_{safe_filename}"
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
        logger.error("Error uploading photos")
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
        logger.error("Error fetching events")
        return jsonify({"success": False, "error": "Failed to fetch events"}), 500


@app.route('/api/events/<event_id>', methods=['PUT'])
def update_event(event_id):
    """
    Update event details (name, location, date, category)
    Requires admin authentication and ownership validation
    """
    # Check admin authentication
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        # Validate required fields
        name = data.get('name')
        location = data.get('location')
        date = data.get('date')
        category = data.get('category')
        
        if not all([name, location, date, category]):
            return jsonify({
                "success": False, 
                "error": "All fields are required (name, location, date, category)"
            }), 400
        
        # Load events data
        if not os.path.exists(EVENTS_DATA_PATH):
            return jsonify({"success": False, "error": "Events data file not found"}), 404
        
        with open(EVENTS_DATA_PATH, 'r') as f:
            events_data = json.load(f)
        
        # Find the event
        event = None
        event_index = None
        for i, e in enumerate(events_data):
            if e['id'] == event_id:
                event = e
                event_index = i
                break
        
        if not event:
            return jsonify({"success": False, "error": "Event not found"}), 404
        
        # Check ownership - admin can only edit their own events
        admin_id = session.get('admin_id')
        if event.get('created_by_admin_id') != admin_id:
            return jsonify({
                "success": False, 
                "error": "You can only edit events you created"
            }), 403
        
        # Update event fields
        event['name'] = name
        event['location'] = location
        event['date'] = date
        event['category'] = category
        
        # Save updated events data
        with open(EVENTS_DATA_PATH, 'w') as f:
            json.dump(events_data, f, indent=2)
        
        return jsonify({
            "success": True,
            "event": event,
            "message": "Event updated successfully"
        }), 200
    
    except Exception as e:
        logger.error("Error updating event")
        return jsonify({
            "success": False, 
            "error": "Failed to update event"
        }), 500


@app.route('/api/events/<event_id>/thumbnail', methods=['POST'])
def update_event_thumbnail(event_id):
    """
    Upload or update event thumbnail
    Requires admin authentication and ownership validation
    """
    # Check admin authentication
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    try:
        # Check if thumbnail file is provided
        if 'thumbnail' not in request.files:
            return jsonify({"success": False, "error": "No thumbnail file provided"}), 400
        
        thumbnail_file = request.files['thumbnail']
        
        if not thumbnail_file or thumbnail_file.filename == '':
            return jsonify({"success": False, "error": "No thumbnail file selected"}), 400
        
        # Validate file upload
        allowed_extensions = {'.png', '.jpg', '.jpeg'}
        is_valid, error_msg = validate_file_upload(thumbnail_file, allowed_extensions, max_size_mb=5)
        
        if not is_valid:
            return jsonify({
                "success": False, 
                "error": error_msg
            }), 400
        
        file_ext = os.path.splitext(thumbnail_file.filename)[1].lower()
        
        # Load events data
        if not os.path.exists(EVENTS_DATA_PATH):
            return jsonify({"success": False, "error": "Events data file not found"}), 404
        
        with open(EVENTS_DATA_PATH, 'r') as f:
            events_data = json.load(f)
        
        # Find the event
        event = None
        event_index = None
        for i, e in enumerate(events_data):
            if e['id'] == event_id:
                event = e
                event_index = i
                break
        
        if not event:
            return jsonify({"success": False, "error": "Event not found"}), 404
        
        # Check ownership - admin can only edit their own events
        admin_id = session.get('admin_id')
        if event.get('created_by_admin_id') != admin_id:
            return jsonify({
                "success": False, 
                "error": "You can only edit events you created"
            }), 403
        
        # Get event upload directory
        event_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
        if not os.path.exists(event_upload_dir):
            os.makedirs(event_upload_dir, exist_ok=True)
        
        # Delete old thumbnail file if it exists
        old_thumbnail_filename = event.get('thumbnail_filename')
        if old_thumbnail_filename:
            old_thumbnail_path = os.path.join(event_upload_dir, old_thumbnail_filename)
            if os.path.exists(old_thumbnail_path):
                try:
                    os.remove(old_thumbnail_path)
                    print(f"Deleted old thumbnail: {old_thumbnail_path}")
                except Exception as e:
                    print(f"Warning: Failed to delete old thumbnail: {e}")
        
        # Generate unique filename with thumbnail_ prefix
        new_thumbnail_filename = f"thumbnail_{uuid.uuid4().hex[:8]}{file_ext}"
        new_thumbnail_path = os.path.join(event_upload_dir, new_thumbnail_filename)
        
        # Save new thumbnail file
        thumbnail_file.save(new_thumbnail_path)
        
        # Update event data with new thumbnail
        event['thumbnail_filename'] = new_thumbnail_filename
        event['image'] = f"/api/events/{event_id}/thumbnail"
        
        # Save updated events data
        with open(EVENTS_DATA_PATH, 'w') as f:
            json.dump(events_data, f, indent=2)
        
        return jsonify({
            "success": True,
            "thumbnail_url": event['image'],
            "message": "Thumbnail updated successfully"
        }), 200
    
    except Exception as e:
        logger.error("Error updating thumbnail")
        return jsonify({
            "success": False, 
            "error": "Failed to update thumbnail"
        }), 500


@app.route('/api/delete_event/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    """
    Delete an event and all associated data (photos, folders, metadata)
    Requires admin authentication and ownership validation
    """
    # Check admin authentication
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    try:
        # Load events data
        if not os.path.exists(EVENTS_DATA_PATH):
            return jsonify({"success": False, "error": "Events data file not found"}), 404
        
        with open(EVENTS_DATA_PATH, 'r') as f:
            events_data = json.load(f)
        
        # Find the event
        event = None
        event_index = None
        for i, e in enumerate(events_data):
            if e['id'] == event_id:
                event = e
                event_index = i
                break
        
        if not event:
            return jsonify({"success": False, "error": "Event not found"}), 404
        
        # Check ownership - admin can only delete their own events
        admin_id = session.get('admin_id')
        if event.get('created_by_admin_id') != admin_id:
            return jsonify({
                "success": False, 
                "error": "You can only delete events you created"
            }), 403
        
        # Delete event folders (uploads and processed)
        upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
        processed_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
        
        # Delete upload folder
        if os.path.exists(upload_dir):
            try:
                shutil.rmtree(upload_dir)
                print(f"Deleted upload folder: {upload_dir}")
            except Exception as e:
                print(f"Warning: Failed to delete upload folder: {e}")
        
        # Delete processed folder
        if os.path.exists(processed_dir):
            try:
                shutil.rmtree(processed_dir)
                print(f"Deleted processed folder: {processed_dir}")
            except Exception as e:
                print(f"Warning: Failed to delete processed folder: {e}")
        
        # Remove event from events_data.json
        events_data.pop(event_index)
        
        # Save updated events data
        with open(EVENTS_DATA_PATH, 'w') as f:
            json.dump(events_data, f, indent=2)
        
        return jsonify({
            "success": True,
            "message": "Event deleted successfully"
        }), 200
    
    except Exception as e:
        print(f"Error deleting event: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "error": "Failed to delete event"
        }), 500


# --- HELPER FUNCTIONS FOR PHOTO AGGREGATION ---
def scan_uploads_folder(event_id):
    """
    Scan uploads folder for original photos.
    Returns list of photo metadata dictionaries.
    
    Args:
        event_id: The event identifier
        
    Returns:
        List of dicts with keys: filename, source, type, url
    """
    photos = []
    uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
    
    logger.info(f"[PHOTO_AGGREGATION] Scanning uploads folder for event: {event_id}")
    
    if not os.path.exists(uploads_dir):
        logger.info(f"[PHOTO_AGGREGATION] Uploads folder does not exist for event: {event_id}")
        return photos
    
    # Filter to only include image files
    allowed_extensions = {'.jpg', '.jpeg', '.png'}
    
    try:
        for filename in os.listdir(uploads_dir):
            # Skip QR codes
            if filename.endswith('_qr.png'):
                logger.debug(f"[PHOTO_AGGREGATION] Skipping QR code: {filename}")
                continue
            
            # Check if file has valid image extension
            ext = os.path.splitext(filename)[1].lower()
            if ext in allowed_extensions:
                photos.append({
                    'filename': filename,
                    'source': 'uploads',
                    'type': 'original',
                    'url': f"/api/events/{event_id}/uploads/{filename}"
                })
                logger.debug(f"[PHOTO_AGGREGATION] Added upload photo: {filename}")
        
        logger.info(f"[PHOTO_AGGREGATION] Found {len(photos)} photos in uploads folder for event: {event_id}")
    except Exception as e:
        logger.error(f"[PHOTO_AGGREGATION] Error scanning uploads folder for event {event_id}: {e}")
    
    return photos


def scan_processed_folder(event_id):
    """
    Scan processed folder for group photos only.
    Individual photos remain private and are not included.
    
    Deduplicates photos by filename - if the same photo appears in multiple
    person folders (because multiple people were detected), it only appears once.
    
    Args:
        event_id: The event identifier
        
    Returns:
        List of dicts with keys: filename, source, type, url
    """
    photos = []
    seen_filenames = set()  # Track filenames to avoid duplicates
    event_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
    
    logger.info(f"[PHOTO_AGGREGATION] Scanning processed folder for event: {event_id}")
    
    if not os.path.exists(event_dir):
        logger.info(f"[PHOTO_AGGREGATION] Processed folder does not exist for event: {event_id}")
        return photos
    
    try:
        person_count = 0
        for person_id in os.listdir(event_dir):
            group_dir = os.path.join(event_dir, person_id, "group")
            if os.path.exists(group_dir):
                person_count += 1
                for filename in os.listdir(group_dir):
                    if filename.startswith('watermarked_'):
                        # Only add if we haven't seen this filename before
                        if filename not in seen_filenames:
                            seen_filenames.add(filename)
                            photos.append({
                                'filename': filename,
                                'source': 'processed',
                                'type': 'group',
                                'url': f"/photos/{event_id}/all/{filename}"
                            })
                            logger.debug(f"[PHOTO_AGGREGATION] Added processed photo: {filename} (person: {person_id})")
                        else:
                            logger.debug(f"[PHOTO_AGGREGATION] Skipping duplicate: {filename} (already added from another person folder)")
        
        logger.info(f"[PHOTO_AGGREGATION] Found {len(photos)} unique processed photos across {person_count} persons for event: {event_id}")
    except Exception as e:
        logger.error(f"[PHOTO_AGGREGATION] Error scanning processed folder for event {event_id}: {e}")
    
    return photos


def deduplicate_photos(processed_photos, uploads_photos):
    """
    Remove duplicate photos based on base filename.
    Prioritizes processed photos over originals when duplicates exist.
    
    The deduplication logic:
    - Strips 'watermarked_' prefix from processed photos for comparison
    - If the same base filename exists in both lists, keeps only the processed version
    - Returns combined list with duplicates removed
    
    Args:
        processed_photos: List of photo dicts from processed folder
        uploads_photos: List of photo dicts from uploads folder
        
    Returns:
        Deduplicated list of photo dicts
    """
    logger.info(f"[PHOTO_AGGREGATION] Deduplicating photos: {len(processed_photos)} processed, {len(uploads_photos)} uploads")
    
    # Build a set of base filenames from processed photos
    processed_base_names = set()
    for photo in processed_photos:
        filename = photo['filename']
        # Remove watermarked_ prefix to get base filename
        if filename.startswith('watermarked_'):
            base_name = filename[len('watermarked_'):]
        else:
            base_name = filename
        processed_base_names.add(base_name)
    
    logger.debug(f"[PHOTO_AGGREGATION] Processed base filenames: {processed_base_names}")
    
    # Filter uploads to exclude any that have processed versions
    filtered_uploads = []
    duplicates_removed = 0
    for photo in uploads_photos:
        if photo['filename'] not in processed_base_names:
            filtered_uploads.append(photo)
        else:
            duplicates_removed += 1
            logger.debug(f"[PHOTO_AGGREGATION] Removing duplicate upload: {photo['filename']} (processed version exists)")
    
    result = processed_photos + filtered_uploads
    logger.info(f"[PHOTO_AGGREGATION] Deduplication complete: {len(result)} total photos ({duplicates_removed} duplicates removed)")
    
    # Combine processed photos (all) with filtered uploads
    return result


# --- PUBLIC & PRIVATE PHOTO SERVING ---
@app.route('/api/events/<event_id>/photos', methods=['GET'])
def get_event_photos(event_id):
    """
    Get all photos for an event - ONLY processed group photos (watermarked).
    
    This endpoint returns only processed group photos to ensure:
    - No duplicate photos in the public gallery
    - Individual photos remain private (not publicly visible)
    - Only watermarked group photos are shown
    
    Individual photos are only accessible through the authenticated biometric portal.
    """
    # Store original value for logging
    original_event_id = event_id
    
    # Sanitize event_id to prevent path traversal
    event_id = sanitize_path_component(event_id)
    
    # Log if sanitization changed the value (potential security violation)
    if event_id != original_event_id:
        logger.warning(f"[SECURITY] Path sanitization applied - original_event_id: {original_event_id}, sanitized_event_id: {event_id}, operation: get_event_photos")
    
    logger.info(f"[PHOTO_AGGREGATION] Getting photos for event: {event_id}, operation: get_event_photos")
    
    try:
        # Only scan processed folder for group photos (watermarked)
        # Do NOT include uploads folder to avoid duplicates and privacy issues
        processed_photos = scan_processed_folder(event_id)
        
        # Handle empty case
        if not processed_photos:
            logger.info(f"[PHOTO_AGGREGATION] No processed photos found for event: {event_id}, operation: get_event_photos")
            return jsonify({
                "success": True,
                "photos": [],
                "has_next": False,
                "message": "No photos available for this event yet. Photos will appear here after processing."
            })
        
        # Sort by filename for consistent ordering
        processed_photos.sort(key=lambda x: x['filename'])
        
        # Extract URLs for response (maintaining backward compatibility)
        photo_urls = [photo['url'] for photo in processed_photos]
        
        logger.info(f"[PHOTO_AGGREGATION] Returning {len(photo_urls)} processed group photos for event: {event_id}, operation: get_event_photos")
        
        return jsonify({
            "success": True,
            "photos": photo_urls,
            "has_next": False
        })
    except Exception as e:
        logger.error(f"[PHOTO_AGGREGATION] Error getting event photos - event_id: {event_id}, error: {str(e)}, operation: get_event_photos")
        import traceback
        logger.error(f"[PHOTO_AGGREGATION] Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": "Failed to retrieve photos"
        }), 500


@app.route('/photos/<event_id>/all/<filename>')
def get_public_photo(event_id, filename):
    # Store original values for logging
    original_event_id = event_id
    original_filename = filename
    
    logger.info(f"[PHOTO_SERVING] Request for public photo - event_id: {event_id}, filename: {filename}, operation: serve_public")
    
    # Sanitize path components to prevent path traversal
    event_id = sanitize_path_component(event_id)
    filename = sanitize_filename(filename)
    
    # Log if sanitization changed the values (potential security violation)
    if event_id != original_event_id or filename != original_filename:
        logger.warning(f"[SECURITY] Path sanitization applied - original_event_id: {original_event_id}, sanitized_event_id: {event_id}, original_filename: {original_filename}, sanitized_filename: {filename}, operation: serve_public")
    
    event_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
    if not os.path.exists(event_dir):
        logger.error(f"[PHOTO_SERVING] Event directory not found - event_id: {event_id}, filename: {filename}, path: {event_dir}, operation: serve_public")
        return "File Not Found", 404
    
    try:
        for person_id in os.listdir(event_dir):
            person_id = sanitize_path_component(person_id)
            photo_path = os.path.join(event_dir, person_id, "group", filename)
            if os.path.exists(photo_path):
                logger.info(f"[PHOTO_SERVING] Successfully serving public photo - event_id: {event_id}, filename: {filename}, person_id: {person_id}, operation: serve_public")
                return send_from_directory(
                    os.path.join(event_dir, person_id, "group"),
                    filename
                )
        
        logger.error(f"[PHOTO_SERVING] File not found in any person directory - event_id: {event_id}, filename: {filename}, operation: serve_public")
        return "File Not Found", 404
    except Exception as e:
        logger.error(f"[PHOTO_SERVING] Error serving public photo - event_id: {event_id}, filename: {filename}, error: {str(e)}, operation: serve_public")
        return "Internal Server Error", 500


@app.route('/photos/<event_id>/<person_id>/<photo_type>/<filename>')
def get_private_photo(event_id, person_id, photo_type, filename):
    # Allow access for admins or logged-in users
    if not session.get('admin_logged_in') and not session.get('logged_in'):
        logger.warning(f"[PHOTO_SERVING] Unauthorized access attempt - event_id: {event_id}, person_id: {person_id}, photo_type: {photo_type}, filename: {filename}, operation: serve_private")
        return "Unauthorized", 401

    # Store original values for logging
    original_event_id = event_id
    original_person_id = person_id
    original_photo_type = photo_type
    original_filename = filename
    
    logger.info(f"[PHOTO_SERVING] Request for private photo - event_id: {event_id}, person_id: {person_id}, photo_type: {photo_type}, filename: {filename}, operation: serve_private")
    
    # Sanitize all path components to prevent path traversal
    event_id = sanitize_path_component(event_id)
    person_id = sanitize_path_component(person_id)
    photo_type = sanitize_path_component(photo_type)
    filename = sanitize_filename(filename)
    
    # Log if sanitization changed the values (potential security violation)
    if (event_id != original_event_id or person_id != original_person_id or 
        photo_type != original_photo_type or filename != original_filename):
        logger.warning(f"[SECURITY] Path sanitization applied - original: {original_event_id}/{original_person_id}/{original_photo_type}/{original_filename}, sanitized: {event_id}/{person_id}/{photo_type}/{filename}, operation: serve_private")
    
    # Validate photo_type is one of the allowed values
    if photo_type not in ['individual', 'group']:
        logger.warning(f"[PHOTO_SERVING] Invalid photo type - event_id: {event_id}, person_id: {person_id}, photo_type: {photo_type}, filename: {filename}, operation: serve_private")
        return "Invalid photo type", 400

    photo_path = os.path.join(
        app.config['PROCESSED_FOLDER'],
        event_id,
        person_id,
        photo_type
    )
    
    full_photo_path = os.path.join(photo_path, filename)
    if not os.path.exists(full_photo_path):
        logger.error(f"[PHOTO_SERVING] File not found - event_id: {event_id}, person_id: {person_id}, photo_type: {photo_type}, filename: {filename}, path: {full_photo_path}, operation: serve_private")
        return "File Not Found", 404
    
    try:
        logger.info(f"[PHOTO_SERVING] Successfully serving private photo - event_id: {event_id}, person_id: {person_id}, photo_type: {photo_type}, filename: {filename}, operation: serve_private")
        return send_from_directory(photo_path, filename)
    except Exception as e:
        logger.error(f"[PHOTO_SERVING] Error serving private photo - event_id: {event_id}, person_id: {person_id}, photo_type: {photo_type}, filename: {filename}, error: {str(e)}, operation: serve_private")
        return "Internal Server Error", 500


@app.route('/api/user_photos', methods=['GET'])
@login_required
def get_user_photos():
    """
    Get all photos for the authenticated user across all events.
    Returns events with photo metadata organized by event.
    """
    try:
        # Validate session is still active
        if not session.get('user_email'):
            return jsonify({
                "success": False,
                "error": "Session expired. Please log in again.",
                "error_code": "SESSION_EXPIRED"
            }), 401
        
        # Get person_id from session (set during face recognition)
        person_id = session.get('person_id')
        
        if not person_id:
            return jsonify({
                "success": False,
                "error": "No person_id found. Please authenticate via biometric scan first.",
                "error_code": "NO_PERSON_ID"
            }), 404

        # Load events metadata with error handling
        events_data = []
        try:
            if os.path.exists(EVENTS_DATA_PATH):
                with open(EVENTS_DATA_PATH, 'r') as f:
                    events_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading events data: {e}")
            # Continue with empty events_data - we'll use defaults

        # Scan processed folder for user's photos across all events
        user_events = []
        total_photos = 0

        if not os.path.exists(app.config['PROCESSED_FOLDER']):
            print(f"Processed folder does not exist: {app.config['PROCESSED_FOLDER']}")
            return jsonify({
                "success": True,
                "events": [],
                "total_photos": 0
            })

        try:
            for event_id in os.listdir(app.config['PROCESSED_FOLDER']):
                event_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
                
                if not os.path.isdir(event_dir):
                    continue

                # Check if this person has photos in this event
                person_dir = os.path.join(event_dir, person_id)
                
                if not os.path.exists(person_dir):
                    continue

                # Get individual and group photos
                individual_dir = os.path.join(person_dir, "individual")
                group_dir = os.path.join(person_dir, "group")

                individual_photos = []
                group_photos = []

                try:
                    if os.path.exists(individual_dir):
                        for filename in os.listdir(individual_dir):
                            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                                individual_photos.append({
                                    "filename": filename,
                                    "url": f"/photos/{event_id}/{person_id}/individual/{filename}"
                                })
                except OSError as e:
                    print(f"Error reading individual photos for {event_id}: {e}")
                    # Continue with empty list

                try:
                    if os.path.exists(group_dir):
                        for filename in os.listdir(group_dir):
                            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                                group_photos.append({
                                    "filename": filename,
                                    "url": f"/photos/{event_id}/{person_id}/group/{filename}"
                                })
                except OSError as e:
                    print(f"Error reading group photos for {event_id}: {e}")
                    # Continue with empty list

                # Only include events where user has photos
                if individual_photos or group_photos:
                    # Find event metadata
                    event_metadata = next(
                        (e for e in events_data if e['id'] == event_id),
                        {
                            "name": event_id,
                            "location": "Unknown",
                            "date": "Unknown",
                            "category": "General"
                        }
                    )

                    event_info = {
                        "event_id": event_id,
                        "event_name": event_metadata.get('name', event_id),
                        "event_date": event_metadata.get('date', 'Unknown'),
                        "event_location": event_metadata.get('location', 'Unknown'),
                        "event_category": event_metadata.get('category', 'General'),
                        "person_id": person_id,
                        "individual_photos": individual_photos,
                        "group_photos": group_photos,
                        "photo_count": len(individual_photos) + len(group_photos)
                    }

                    user_events.append(event_info)
                    total_photos += event_info['photo_count']
        except OSError as e:
            print(f"Error scanning processed folder: {e}")
            return jsonify({
                "success": False,
                "error": "Unable to access photo storage. Please try again later.",
                "error_code": "STORAGE_ERROR"
            }), 500

        # Sort events by date (most recent first)
        user_events.sort(key=lambda x: x['event_date'], reverse=True)

        return jsonify({
            "success": True,
            "events": user_events,
            "total_photos": total_photos
        })

    except Exception as e:
        print(f"Error fetching user photos: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": "An unexpected error occurred while loading your photos. Please try again.",
            "error_code": "INTERNAL_ERROR"
        }), 500


@app.route('/api/download_photos', methods=['POST'])
@login_required
def download_photos():
    """
    Download multiple photos as a ZIP file (for personal gallery)
    """
    zip_path = None
    try:
        import zipfile
        from flask import send_file
        
        # Validate session is still active
        if not session.get('user_email'):
            return jsonify({
                "success": False,
                "error": "Session expired. Please log in again.",
                "error_code": "SESSION_EXPIRED"
            }), 401
        
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False, 
                "error": "Invalid request format",
                "error_code": "INVALID_REQUEST"
            }), 400
            
        event_id = data.get('event_id')
        person_id = data.get('person_id')
        photos = data.get('photos', [])

        if not all([event_id, person_id, photos]):
            return jsonify({
                "success": False, 
                "error": "Missing required parameters (event_id, person_id, or photos)",
                "error_code": "MISSING_PARAMETERS"
            }), 400
        
        # Validate photos is a list
        if not isinstance(photos, list):
            return jsonify({
                "success": False,
                "error": "Invalid photos parameter. Expected a list.",
                "error_code": "INVALID_PHOTOS_FORMAT"
            }), 400
        
        # Validate photos list is not empty
        if len(photos) == 0:
            return jsonify({
                "success": False,
                "error": "No photos selected for download.",
                "error_code": "NO_PHOTOS_SELECTED"
            }), 400

        # Validate photo count and estimate size (max 100MB)
        MAX_PHOTOS = 500
        if len(photos) > MAX_PHOTOS:
            return jsonify({
                "success": False,
                "error": f"Too many photos selected. Maximum is {MAX_PHOTOS} photos per download.",
                "error_code": "TOO_MANY_PHOTOS"
            }), 413

        # Check disk space availability
        try:
            import shutil
            stat = shutil.disk_usage(app.config['PROCESSED_FOLDER'])
            free_space = stat.free
            MIN_FREE_SPACE = 200 * 1024 * 1024  # Require at least 200MB free
            
            if free_space < MIN_FREE_SPACE:
                return jsonify({
                    "success": False,
                    "error": "Insufficient disk space on server. Please try again later.",
                    "error_code": "INSUFFICIENT_DISK_SPACE"
                }), 507
        except Exception as e:
            print(f"Warning: Could not check disk space: {e}")
            # Continue anyway - this is just a precaution
        
        # Create a temporary ZIP file
        zip_filename = f"photos_{event_id}_{person_id}_{uuid.uuid4().hex[:8]}.zip"
        zip_path = os.path.join(app.config['PROCESSED_FOLDER'], zip_filename)

        photos_added = 0
        total_size = 0
        MAX_ZIP_SIZE = 100 * 1024 * 1024  # 100MB

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for photo in photos:
                    # Validate photo object structure
                    if not isinstance(photo, dict):
                        print(f"Invalid photo object: {photo}")
                        continue
                    
                    filename = photo.get('filename')
                    photo_type = photo.get('photoType')
                    
                    if not filename or not photo_type:
                        print(f"Missing filename or photoType: {photo}")
                        continue
                    
                    # Validate photo_type
                    if photo_type not in ['individual', 'group']:
                        print(f"Invalid photo_type: {photo_type}")
                        continue
                    
                    # Remove watermarked_ prefix if present for the actual file
                    actual_filename = filename.replace('watermarked_', '') if filename.startswith('watermarked_') else filename
                    
                    # Sanitize filename to prevent path traversal
                    actual_filename = os.path.basename(actual_filename)
                    
                    photo_path = os.path.join(
                        app.config['PROCESSED_FOLDER'],
                        event_id,
                        person_id,
                        photo_type,
                        filename
                    )

                    if os.path.exists(photo_path):
                        try:
                            # Check file size before adding
                            file_size = os.path.getsize(photo_path)
                            if total_size + file_size > MAX_ZIP_SIZE:
                                print(f"ZIP size limit reached: {total_size} bytes")
                                # Return partial success with warning
                                if photos_added > 0:
                                    break
                                else:
                                    if zip_path and os.path.exists(zip_path):
                                        os.remove(zip_path)
                                    return jsonify({
                                        "success": False,
                                        "error": "Selected photos exceed size limit (100MB). Please select fewer photos.",
                                        "error_code": "ZIP_SIZE_LIMIT"
                                    }), 413
                            
                            # Verify file is readable
                            with open(photo_path, 'rb') as test_file:
                                test_file.read(1)
                            
                            # Add to ZIP with a clean filename
                            zipf.write(photo_path, arcname=actual_filename)
                            photos_added += 1
                            total_size += file_size
                        except (IOError, OSError) as e:
                            print(f"Error reading photo {photo_path}: {e}")
                            continue
                    else:
                        print(f"Photo not found: {photo_path}")
        except zipfile.BadZipFile as e:
            print(f"Bad ZIP file error: {e}")
            if zip_path and os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except:
                    pass
            return jsonify({
                "success": False,
                "error": "Unable to create valid ZIP file. Please try again.",
                "error_code": "BAD_ZIP_FILE"
            }), 500
        except OSError as e:
            print(f"Error creating ZIP file: {e}")
            if zip_path and os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except:
                    pass
            
            # Check if it's a disk space issue
            if "No space left" in str(e) or "Disk quota exceeded" in str(e):
                return jsonify({
                    "success": False,
                    "error": "Server disk space full. Please try again later or select fewer photos.",
                    "error_code": "DISK_FULL"
                }), 507
            
            return jsonify({
                "success": False,
                "error": "Unable to create download file. Please try again.",
                "error_code": "ZIP_CREATION_ERROR"
            }), 500
        except MemoryError as e:
            print(f"Memory error creating ZIP: {e}")
            if zip_path and os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except:
                    pass
            return jsonify({
                "success": False,
                "error": "Too many photos selected. Please select fewer photos.",
                "error_code": "MEMORY_ERROR"
            }), 413

        if photos_added == 0:
            # Clean up empty ZIP
            if os.path.exists(zip_path):
                os.remove(zip_path)
            return jsonify({
                "success": False,
                "error": "No photos were found to download. They may have been deleted.",
                "error_code": "NO_PHOTOS_FOUND"
            }), 404

        # Verify ZIP file exists and has content
        if not os.path.exists(zip_path) or os.path.getsize(zip_path) == 0:
            return jsonify({
                "success": False,
                "error": "Failed to create download file",
                "error_code": "EMPTY_ZIP"
            }), 500

        # Send the ZIP file
        try:
            response = send_file(
                zip_path,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"picme_photos_{event_id}.zip"
            )
        except Exception as e:
            print(f"Error sending ZIP file: {e}")
            if zip_path and os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except:
                    pass
            return jsonify({
                "success": False,
                "error": "Failed to send download file",
                "error_code": "SEND_ERROR"
            }), 500

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
        import traceback
        traceback.print_exc()
        
        # Clean up ZIP file on error
        if zip_path and os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except:
                pass
                
        return jsonify({
            "success": False,
            "error": "An unexpected error occurred during download. Please try again.",
            "error_code": "INTERNAL_ERROR"
        }), 500


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
        logger.warning(f"[PHOTO_SERVING] Unauthorized admin access attempt - event_id: {event_id}, filename: {filename}, operation: serve_admin")
        return "Unauthorized", 403

    # Store original values for logging
    original_event_id = event_id
    original_filename = filename
    
    logger.info(f"[PHOTO_SERVING] Admin request for photo - event_id: {event_id}, filename: {filename}, operation: serve_admin")
    
    # Sanitize path components to prevent path traversal
    event_id = sanitize_path_component(event_id)
    filename = sanitize_filename(filename)
    
    # Log if sanitization changed the values (potential security violation)
    if event_id != original_event_id or filename != original_filename:
        logger.warning(f"[SECURITY] Path sanitization applied - original_event_id: {original_event_id}, sanitized_event_id: {event_id}, original_filename: {original_filename}, sanitized_filename: {filename}, operation: serve_admin")

    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
    full_path = os.path.join(upload_dir, filename)
    
    if os.path.exists(full_path):
        try:
            logger.info(f"[PHOTO_SERVING] Successfully serving admin photo - event_id: {event_id}, filename: {filename}, operation: serve_admin")
            return send_from_directory(upload_dir, filename)
        except Exception as e:
            logger.error(f"[PHOTO_SERVING] Error serving admin photo - event_id: {event_id}, filename: {filename}, error: {str(e)}, operation: serve_admin")
            return "Internal Server Error", 500
    
    logger.error(f"[PHOTO_SERVING] File not found - event_id: {event_id}, filename: {filename}, path: {full_path}, operation: serve_admin")
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


@app.route('/api/events/<event_id>/uploads/<filename>')
def serve_upload_photo(event_id, filename):
    """
    Serve photos directly from uploads folder.
    This endpoint provides access to original uploaded photos before processing.
    
    Security measures:
    - Sanitizes event_id to prevent path traversal
    - Sanitizes filename to prevent directory traversal
    - Validates file extension is in allowed list
    - Verifies file exists before serving
    - Only serves files from within uploads directory
    """
    # Store original values for logging
    original_event_id = event_id
    original_filename = filename
    
    logger.info(f"[PHOTO_SERVING] Request for upload photo - event_id: {event_id}, filename: {filename}, operation: serve_upload")
    
    # Sanitize inputs to prevent path traversal attacks
    event_id = sanitize_path_component(event_id)
    filename = sanitize_filename(filename)
    
    # Log if sanitization changed the values (potential security violation)
    if event_id != original_event_id or filename != original_filename:
        logger.warning(f"[SECURITY] Path sanitization applied - original_event_id: {original_event_id}, sanitized_event_id: {event_id}, original_filename: {original_filename}, sanitized_filename: {filename}, operation: serve_upload")
    
    # Validate file extension is in allowed list
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png']:
        logger.warning(f"[PHOTO_SERVING] Invalid file type rejected - event_id: {event_id}, filename: {filename}, extension: {ext}, operation: serve_upload")
        return "Invalid file type", 400
    
    # Build path to uploads folder for this event
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
    photo_path = os.path.join(upload_dir, filename)
    
    # Verify file exists before attempting to serve
    if not os.path.exists(photo_path):
        logger.error(f"[PHOTO_SERVING] File not found - event_id: {event_id}, filename: {filename}, path: {photo_path}, operation: serve_upload")
        return "File Not Found", 404
    
    # Verify the resolved path is still within the uploads directory (additional security check)
    real_upload_dir = os.path.realpath(upload_dir)
    real_photo_path = os.path.realpath(photo_path)
    if not real_photo_path.startswith(real_upload_dir):
        logger.error(f"[SECURITY] Path traversal attempt detected - event_id: {event_id}, filename: {filename}, attempted_path: {photo_path}, operation: serve_upload")
        return "File Not Found", 404
    
    # Serve file securely using Flask's send_from_directory
    try:
        logger.info(f"[PHOTO_SERVING] Successfully serving upload photo - event_id: {event_id}, filename: {filename}, operation: serve_upload")
        return send_from_directory(upload_dir, filename)
    except Exception as e:
        logger.error(f"[PHOTO_SERVING] Error serving file - event_id: {event_id}, filename: {filename}, error: {str(e)}, operation: serve_upload")
        return "Internal Server Error", 500


# --- STARTUP TASKS ---
def process_existing_uploads_on_startup():
    print("--- [LOG] Checking for existing photos on startup... ---")
    if os.path.exists(UPLOAD_FOLDER):
        for event_id in os.listdir(UPLOAD_FOLDER):
            if os.path.isdir(os.path.join(UPLOAD_FOLDER, event_id)):
                threading.Thread(target=process_images, args=(event_id,)).start()


# --- ENTRY POINT ---
if __name__ == '__main__':
    # Auto-generate known_faces.dat if it doesn't exist and there are photos to process
    if not os.path.exists(KNOWN_FACES_DATA_PATH):
        logger.info("known_faces.dat not found. Checking for photos to process...")
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
            logger.info("Photos found. Auto-generating face recognition model...")
            process_existing_uploads_on_startup()
            logger.info("Face recognition model generation started in background.")
        else:
            logger.info("No photos found. Face recognition model will be created when photos are uploaded.")
    else:
        logger.info("Face recognition model loaded successfully.")

    # Use PORT from environment variable (already set at top of file)
    # Use 0.0.0.0 for container compatibility (allows external connections)
    logger.info(f"Starting Flask application on 0.0.0.0:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=True)
