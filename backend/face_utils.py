import cv2
import numpy as np
import face_recognition
import dlib

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREDICTOR_PATH = os.path.join(BASE_DIR, "shape_predictor_68_face_landmarks.dat")

predictor = dlib.shape_predictor(PREDICTOR_PATH)



def align_face(image):
    """
    Aligns the face by rotating based on eye angle.
    Returns aligned image or None if face cannot be detected.
    """
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb)

    if not face_locations:
        return None

    top, right, bottom, left = face_locations[0]
    rect = dlib.rectangle(left, top, right, bottom)

    shape = predictor(rgb, rect)
    points = np.array([(shape.part(i).x, shape.part(i).y) for i in range(68)])

    left_eye = points[36:42].mean(axis=0)
    right_eye = points[42:48].mean(axis=0)

    dy = right_eye[1] - left_eye[1]
    dx = right_eye[0] - left_eye[0]
    angle = np.degrees(np.arctan2(dy, dx))

    # Rotate around image center
    h, w = image.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1)
    aligned = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC)

    return aligned


def compute_frame_quality(frame):
    """
    Calculate clarity + brightness, returns score from 0 to 1.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
    brightness = np.mean(gray)

    sharp_norm = min(1.0, sharpness / 80.0)     # sharp threshold
    bright_norm = min(1.0, brightness / 150.0)  # brightness threshold

    return (sharp_norm * 0.7) + (bright_norm * 0.3)


def aggregate_face_encoding_from_bgr_frames(frames):
    """
    Build a strong prediction using multiple frames.
    Weighted average based on blur + brightness score.
    """
    encodings = []
    weights = []

    for frame in frames:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_enc = face_recognition.face_encodings(rgb)

        if len(face_enc) == 0:
            aligned = align_face(frame)
            if aligned is not None:
                rgb2 = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB)
                face_enc = face_recognition.face_encodings(rgb2)

        if len(face_enc) == 0:
            continue

        weight = compute_frame_quality(frame)
        if weight < 0.15:
            continue

        encodings.append(face_enc[0])
        weights.append(weight)

    if not encodings:
        return None

    encodings = np.array(encodings)
    weights = np.array(weights).reshape(-1, 1)

    final_encoding = np.sum(encodings * weights, axis=0) / np.sum(weights)
    return final_encoding


# ----------------------------------------------------------------------
# LIVENESS + SPOOF DETECTION (blink + head turn + motion)
# ----------------------------------------------------------------------

def _eye_aspect_ratio(eye_points):
    """
    Compute Eye Aspect Ratio for one eye (6 landmark points).
    """
    p2_minus_p6 = np.linalg.norm(eye_points[1] - eye_points[5])
    p3_minus_p5 = np.linalg.norm(eye_points[2] - eye_points[4])
    p1_minus_p4 = np.linalg.norm(eye_points[0] - eye_points[3])

    if p1_minus_p4 == 0:
        return 0.0
    ear = (p2_minus_p6 + p3_minus_p5) / (2.0 * p1_minus_p4)
    return ear


def verify_liveness_from_bgr_frames(frames, challenge_type=None):
    """
    Basic liveness and anti-spoofing using:
      - Eye blink detection
      - Head turn (left/right) based on face center movement
      - Motion amount between frames (reject static images)

    challenge_type:
      - "BLINK"
      - "HEAD_TURN"
      - None / anything else -> accept BLINK or HEAD_TURN

    Returns: (is_live: bool, debug_info: dict)
    """
    if not frames or len(frames) < 2:
        return False, {"reason": "Not enough frames for liveness"}

    # Thresholds tuned to be reasonably strict but not crazy
    EAR_OPEN = 0.24
    EAR_CLOSED = 0.19
    MOTION_MIN = 3.5        # average pixel difference for motion
    TURN_MIN = 0.22         # relative center shift vs face width

    blink_count = 0
    prev_state = "OPEN"
    centers_x = []
    widths = []
    motion_scores = []

    prev_gray = None

    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Motion (spoof) analysis
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            motion_scores.append(float(np.mean(diff)))
        prev_gray = gray

        # Face + landmarks
        locations = face_recognition.face_locations(rgb)
        if not locations:
            continue

        top, right, bottom, left = locations[0]
        rect = dlib.rectangle(left, top, right, bottom)
        shape = predictor(gray, rect)
        points = np.array([(shape.part(i).x, shape.part(i).y) for i in range(68)])

        # Eyes
        left_eye_pts = points[36:42]
        right_eye_pts = points[42:48]
        ear_left = _eye_aspect_ratio(left_eye_pts)
        ear_right = _eye_aspect_ratio(right_eye_pts)
        ear = (ear_left + ear_right) / 2.0

        # Blink state machine (OPEN -> CLOSED -> OPEN = 1 blink)
        if ear < EAR_CLOSED and prev_state == "OPEN":
            prev_state = "CLOSED"
        elif ear > EAR_OPEN and prev_state == "CLOSED":
            blink_count += 1
            prev_state = "OPEN"

        # Head movement: track horizontal center of face
        cx = (left + right) / 2.0
        w = (right - left)
        centers_x.append(cx)
        widths.append(w)

    avg_motion = float(np.mean(motion_scores)) if motion_scores else 0.0

    head_turn_score = 0.0
    if centers_x and widths:
        shift = max(centers_x) - min(centers_x)
        avg_width = float(np.mean(widths)) if widths else 1.0
        if avg_width <= 0:
            avg_width = 1.0
        head_turn_score = shift / avg_width

    motion_ok = avg_motion >= MOTION_MIN
    blink_ok = blink_count >= 1
    head_turn_ok = head_turn_score >= TURN_MIN

    # Decide based on challenge
    ct = (challenge_type or "").upper()
    if ct == "BLINK":
        passed = motion_ok and blink_ok
    elif ct == "HEAD_TURN":
        passed = motion_ok and head_turn_ok
    else:
        # Random mode: accept either blink or head turn, but always require motion
        passed = motion_ok and (blink_ok or head_turn_ok)

    debug = {
        "challenge_type": ct or "AUTO",
        "blink_count": blink_count,
        "avg_motion": round(avg_motion, 3),
        "head_turn_score": round(head_turn_score, 3),
        "motion_ok": motion_ok,
        "blink_ok": blink_ok,
        "head_turn_ok": head_turn_ok,
        "passed": passed,
    }

    return passed, debug
