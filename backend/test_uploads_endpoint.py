"""
Tests for uploads photo serving endpoint.

These tests validate that the /api/events/<event_id>/uploads/<filename> endpoint
works correctly and implements proper security measures.

**Validates: Requirements 2.4, 3.1, 3.2, 3.3, 3.4, 3.5**
"""

import pytest
import os
import sys
import tempfile

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Flask app
from app import app as flask_app


# ============================================================================
# Test Setup and Fixtures
# ============================================================================

@pytest.fixture
def client():
    """
    Create a test client for the Flask application.
    """
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'test_secret_key'
    
    # Use temporary directories for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        flask_app.config['UPLOAD_FOLDER'] = os.path.join(temp_dir, 'uploads')
        flask_app.config['PROCESSED_FOLDER'] = os.path.join(temp_dir, 'processed')
        
        os.makedirs(flask_app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(flask_app.config['PROCESSED_FOLDER'], exist_ok=True)
        
        with flask_app.test_client() as client:
            yield client


@pytest.fixture
def event_with_photo(client):
    """
    Create a test event with a photo in the uploads folder.
    """
    event_id = 'test_event_123'
    event_dir = os.path.join(flask_app.config['UPLOAD_FOLDER'], event_id)
    os.makedirs(event_dir, exist_ok=True)
    
    # Create a dummy photo file
    photo_filename = 'test_photo.jpg'
    photo_path = os.path.join(event_dir, photo_filename)
    with open(photo_path, 'wb') as f:
        f.write(b'fake image data')
    
    return {
        'event_id': event_id,
        'filename': photo_filename,
        'path': photo_path
    }


# ============================================================================
# Uploads Endpoint Tests
# ============================================================================

def test_serve_upload_photo_success(client, event_with_photo):
    """
    Test that the uploads endpoint serves photos successfully.
    
    **Validates: Requirements 2.4**
    """
    response = client.get(
        f"/api/events/{event_with_photo['event_id']}/uploads/{event_with_photo['filename']}"
    )
    
    assert response.status_code == 200, \
        "Uploads endpoint should return 200 OK for valid photo"
    
    assert response.data == b'fake image data', \
        "Uploads endpoint should return the correct file content"


def test_serve_upload_photo_validates_extension(client, event_with_photo):
    """
    Test that the uploads endpoint validates file extensions.
    
    **Validates: Requirements 3.1, 3.2**
    """
    # Create a file with invalid extension
    event_dir = os.path.join(flask_app.config['UPLOAD_FOLDER'], event_with_photo['event_id'])
    invalid_file = os.path.join(event_dir, 'test.txt')
    with open(invalid_file, 'wb') as f:
        f.write(b'text file')
    
    response = client.get(
        f"/api/events/{event_with_photo['event_id']}/uploads/test.txt"
    )
    
    assert response.status_code == 400, \
        "Uploads endpoint should reject invalid file extensions"
    
    assert b'Invalid file type' in response.data, \
        "Error message should indicate invalid file type"


def test_serve_upload_photo_file_not_found(client):
    """
    Test that the uploads endpoint returns 404 for non-existent files.
    
    **Validates: Requirements 3.3, 3.4**
    """
    response = client.get(
        "/api/events/test_event/uploads/nonexistent.jpg"
    )
    
    assert response.status_code == 404, \
        "Uploads endpoint should return 404 for non-existent files"
    
    assert b'File Not Found' in response.data, \
        "Error message should indicate file not found"


def test_serve_upload_photo_sanitizes_event_id(client, event_with_photo):
    """
    Test that the uploads endpoint sanitizes event_id to prevent path traversal.
    
    **Validates: Requirements 3.1, 3.5**
    """
    # Try path traversal in event_id
    response = client.get(
        f"/api/events/../../../etc/uploads/{event_with_photo['filename']}"
    )
    
    assert response.status_code == 404, \
        "Uploads endpoint should reject path traversal attempts in event_id"


def test_serve_upload_photo_sanitizes_filename(client, event_with_photo):
    """
    Test that the uploads endpoint sanitizes filename to prevent directory traversal.
    
    **Validates: Requirements 3.2, 3.5**
    """
    # Try path traversal in filename
    response = client.get(
        f"/api/events/{event_with_photo['event_id']}/uploads/../../etc/passwd"
    )
    
    assert response.status_code == 404, \
        "Uploads endpoint should reject path traversal attempts in filename"


def test_serve_upload_photo_accepts_valid_extensions(client, event_with_photo):
    """
    Test that the uploads endpoint accepts all valid image extensions.
    
    **Validates: Requirements 2.4**
    """
    event_dir = os.path.join(flask_app.config['UPLOAD_FOLDER'], event_with_photo['event_id'])
    
    valid_extensions = ['.jpg', '.jpeg', '.png']
    
    for ext in valid_extensions:
        filename = f'test{ext}'
        filepath = os.path.join(event_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(b'fake image data')
        
        response = client.get(
            f"/api/events/{event_with_photo['event_id']}/uploads/{filename}"
        )
        
        assert response.status_code == 200, \
            f"Uploads endpoint should accept {ext} files"


def test_serve_upload_photo_directory_containment(client, event_with_photo):
    """
    Test that the uploads endpoint only serves files from within uploads directory.
    
    **Validates: Requirements 3.5**
    """
    # This test verifies the realpath check prevents serving files outside uploads
    # Even if sanitization is bypassed, the realpath check should catch it
    
    response = client.get(
        f"/api/events/{event_with_photo['event_id']}/uploads/....//....//etc//passwd"
    )
    
    assert response.status_code == 404, \
        "Uploads endpoint should not serve files outside uploads directory"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
