"""
Property-based tests for photo serving endpoints.

These tests use Hypothesis to verify correctness properties across
a wide range of inputs, ensuring the photo serving infrastructure
handles all valid cases correctly and rejects invalid inputs safely.

**Feature: photo-serving-fix**
"""

import pytest
import os
import sys
import tempfile
import string
from hypothesis import given, strategies as st, settings, assume

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Flask app
from app import app as flask_app


# ============================================================================
# Test Setup and Fixtures
# ============================================================================

def get_test_client():
    """
    Create a test client for the Flask application.
    Returns a context manager that yields the client.
    """
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'test_secret_key'
    
    # Use temporary directories for testing
    temp_dir = tempfile.mkdtemp()
    flask_app.config['UPLOAD_FOLDER'] = os.path.join(temp_dir, 'uploads')
    flask_app.config['PROCESSED_FOLDER'] = os.path.join(temp_dir, 'processed')
    
    os.makedirs(flask_app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(flask_app.config['PROCESSED_FOLDER'], exist_ok=True)
    
    return flask_app.test_client(), temp_dir


# ============================================================================
# Hypothesis Strategies
# ============================================================================

# Windows reserved names that cannot be used as filenames or directory names
WINDOWS_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
}

def is_valid_windows_name(name):
    """Check if a name is valid on Windows (not a reserved name)."""
    return name.upper() not in WINDOWS_RESERVED_NAMES

# Valid event ID strategy: alphanumeric with underscores, excluding Windows reserved names
valid_event_id_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + '_',
    min_size=1,
    max_size=50
).filter(is_valid_windows_name)

# Valid filename strategy: alphanumeric with dots, dashes, underscores
# Must end with valid image extension, excluding Windows reserved names
valid_filename_base_strategy = st.text(
    alphabet=string.ascii_letters + string.digits + '_-',
    min_size=1,
    max_size=50
).filter(is_valid_windows_name)

valid_extension_strategy = st.sampled_from(['.jpg', '.jpeg', '.png'])

# Path traversal characters for security testing
path_traversal_chars = st.sampled_from(['../', '..\\', '/', '\\', '\x00', '..'])


# ============================================================================
# Property 1: Photo serving returns valid responses
# Feature: photo-serving-fix, Property 1: Photo serving returns valid responses
# **Validates: Requirements 1.1, 1.3**
# ============================================================================

@settings(max_examples=100)
@given(
    event_id=valid_event_id_strategy,
    filename_base=valid_filename_base_strategy,
    extension=valid_extension_strategy,
    file_content=st.binary(min_size=1, max_size=1024)
)
def test_property_photo_serving_returns_valid_responses(event_id, filename_base, extension, file_content):
    """
    Property 1: Photo serving returns valid responses
    
    For any valid event_id and filename combination that exists in the uploads folder,
    requesting the photo via /api/events/{event_id}/uploads/{filename} should return
    a 200 status code with the photo file content.
    
    **Feature: photo-serving-fix, Property 1: Photo serving returns valid responses**
    **Validates: Requirements 1.1, 1.3**
    """
    import shutil
    
    # Get test client
    client, temp_dir = get_test_client()
    
    try:
        # Construct valid filename with extension
        filename = filename_base + extension
        
        # Create event directory
        event_dir = os.path.join(flask_app.config['UPLOAD_FOLDER'], event_id)
        os.makedirs(event_dir, exist_ok=True)
        
        # Create photo file with content
        photo_path = os.path.join(event_dir, filename)
        with open(photo_path, 'wb') as f:
            f.write(file_content)
        
        # Request the photo
        response = client.get(f"/api/events/{event_id}/uploads/{filename}")
        
        # Verify response
        assert response.status_code == 200, \
            f"Photo serving should return 200 OK for valid photo (event_id={event_id}, filename={filename})"
        
        assert response.data == file_content, \
            f"Photo serving should return the correct file content"
        
        # Verify correct MIME type is set (Flask's send_from_directory handles this)
        content_type = response.headers.get('Content-Type', '')
        assert any(mime in content_type for mime in ['image/jpeg', 'image/png', 'image/jpg']), \
            f"Photo serving should set appropriate MIME type, got: {content_type}"
    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])



# ============================================================================
# Property 2: Path sanitization prevents traversal
# Feature: photo-serving-fix, Property 2: Path sanitization prevents traversal
# **Validates: Requirements 1.2**
# ============================================================================

# Strategy for generating path traversal attempts
path_traversal_strategy = st.one_of(
    # Basic path traversal patterns
    st.just('../'),
    st.just('..\\'),
    st.just('../../'),
    st.just('..\\..\\'),
    st.just('../../../'),
    # Null byte injection
    st.just('\x00'),
    # Mixed patterns
    st.text(min_size=1, max_size=20).map(lambda s: f"../{s}"),
    st.text(min_size=1, max_size=20).map(lambda s: f"..\\{s}"),
    st.text(min_size=1, max_size=20).map(lambda s: f"{s}/../"),
    st.text(min_size=1, max_size=20).map(lambda s: f"{s}/.."),
    # Absolute paths
    st.just('/etc/passwd'),
    st.just('C:\\Windows\\System32'),
    # URL encoded traversal
    st.just('%2e%2e%2f'),
    st.just('%2e%2e/'),
)


@settings(max_examples=100)
@given(
    event_id_traversal=path_traversal_strategy,
    filename_traversal=path_traversal_strategy,
)
def test_property_path_sanitization_prevents_traversal(event_id_traversal, filename_traversal):
    """
    Property 2: Path sanitization prevents traversal
    
    For any event_id or filename containing path traversal characters (../, ..\\, /, \\),
    the system should sanitize them before file system operations, preventing access to
    files outside the intended directories.
    
    **Feature: photo-serving-fix, Property 2: Path sanitization prevents traversal**
    **Validates: Requirements 1.2**
    """
    import shutil
    
    # Get test client
    client, temp_dir = get_test_client()
    
    try:
        # Test path traversal in event_id
        response = client.get(f"/api/events/{event_id_traversal}/uploads/test.jpg")
        
        # Should NOT return 200 (successful file serving)
        # Can return 404 (not found), 400 (bad request), 308 (redirect), or other error codes
        # The key is that it should NOT successfully serve a file
        assert response.status_code != 200, \
            f"Path traversal in event_id should not successfully serve files, got status {response.status_code}"
        
        # Test path traversal in filename
        response = client.get(f"/api/events/test_event/uploads/{filename_traversal}")
        
        # Should NOT return 200 (successful file serving)
        assert response.status_code != 200, \
            f"Path traversal in filename should not successfully serve files, got status {response.status_code}"
        
        # Test combined path traversal (both event_id and filename)
        response = client.get(f"/api/events/{event_id_traversal}/uploads/{filename_traversal}")
        
        # Should NOT return 200 (successful file serving)
        assert response.status_code != 200, \
            f"Combined path traversal should not successfully serve files, got status {response.status_code}"
        
    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


@settings(max_examples=100)
@given(
    valid_event_id=valid_event_id_strategy,
    valid_filename_base=valid_filename_base_strategy,
    valid_extension=valid_extension_strategy,
)
def test_property_sanitization_does_not_break_valid_paths(valid_event_id, valid_filename_base, valid_extension):
    """
    Property 2 (complementary): Sanitization does not break valid paths
    
    For any valid event_id and filename (without path traversal characters),
    the sanitization should not alter them, and the endpoint should work correctly.
    
    This ensures that sanitization only affects malicious inputs, not legitimate ones.
    
    **Feature: photo-serving-fix, Property 2: Path sanitization prevents traversal**
    **Validates: Requirements 1.2**
    """
    import shutil
    
    # Get test client
    client, temp_dir = get_test_client()
    
    try:
        # Construct valid filename
        filename = valid_filename_base + valid_extension
        
        # Create event directory and photo
        event_dir = os.path.join(flask_app.config['UPLOAD_FOLDER'], valid_event_id)
        os.makedirs(event_dir, exist_ok=True)
        
        photo_path = os.path.join(event_dir, filename)
        test_content = b'test photo content'
        with open(photo_path, 'wb') as f:
            f.write(test_content)
        
        # Request the photo
        response = client.get(f"/api/events/{valid_event_id}/uploads/{filename}")
        
        # Should return 200 OK with correct content
        assert response.status_code == 200, \
            f"Valid paths should not be affected by sanitization (event_id={valid_event_id}, filename={filename})"
        
        assert response.data == test_content, \
            f"Sanitization should not corrupt valid file content"
        
    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
