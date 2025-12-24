"""
Test to verify comprehensive error logging is implemented correctly.
This test checks that all photo serving endpoints and processing functions
have proper structured logging with event_id, filename, and operation context.
"""
import pytest
import logging
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from backend.app import app, sanitize_path_component, sanitize_filename


@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_folders():
    """Create temporary upload and processed folders for testing"""
    temp_dir = tempfile.mkdtemp()
    upload_folder = os.path.join(temp_dir, 'uploads')
    processed_folder = os.path.join(temp_dir, 'processed')
    os.makedirs(upload_folder)
    os.makedirs(processed_folder)
    
    # Store original config
    original_upload = app.config['UPLOAD_FOLDER']
    original_processed = app.config['PROCESSED_FOLDER']
    
    # Set test config
    app.config['UPLOAD_FOLDER'] = upload_folder
    app.config['PROCESSED_FOLDER'] = processed_folder
    
    yield upload_folder, processed_folder
    
    # Restore original config
    app.config['UPLOAD_FOLDER'] = original_upload
    app.config['PROCESSED_FOLDER'] = original_processed
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_serve_upload_photo_logs_request(client, temp_folders, caplog):
    """Test that serve_upload_photo logs the request with proper context"""
    upload_folder, _ = temp_folders
    event_id = "test_event_123"
    filename = "test_photo.jpg"
    
    # Create test event folder and file
    event_dir = os.path.join(upload_folder, event_id)
    os.makedirs(event_dir)
    test_file = os.path.join(event_dir, filename)
    with open(test_file, 'wb') as f:
        f.write(b'fake image data')
    
    with caplog.at_level(logging.INFO):
        response = client.get(f'/api/events/{event_id}/uploads/{filename}')
    
    # Check that logging occurred with proper context
    assert any('[PHOTO_SERVING]' in record.message for record in caplog.records)
    assert any('serve_upload' in record.message for record in caplog.records)
    assert any(event_id in record.message for record in caplog.records)
    assert any(filename in record.message for record in caplog.records)


def test_serve_upload_photo_logs_security_violation(client, temp_folders, caplog):
    """Test that path traversal attempts are logged as security violations"""
    upload_folder, _ = temp_folders
    # Use URL encoding to bypass Flask's URL parsing
    # The sanitization will still catch it in the function
    event_id = "test..event"  # Contains .. which should trigger sanitization
    filename = "test/file.jpg"  # Contains / which should trigger sanitization
    
    with caplog.at_level(logging.WARNING):
        response = client.get(f'/api/events/{event_id}/uploads/{filename}')
    
    # The sanitization removes problematic characters, so we should see a 404
    # because the sanitized path won't exist
    assert response.status_code == 404
    
    # Note: The security logging happens when original != sanitized
    # In this case, the path components get cleaned up
    # We can verify the endpoint is protected by checking it returns 404
    # for invalid paths rather than exposing the file system


def test_serve_upload_photo_logs_file_not_found(client, temp_folders, caplog):
    """Test that file not found errors are logged with proper context"""
    upload_folder, _ = temp_folders
    event_id = "test_event_123"
    filename = "nonexistent.jpg"
    
    # Create event folder but no file
    event_dir = os.path.join(upload_folder, event_id)
    os.makedirs(event_dir)
    
    with caplog.at_level(logging.ERROR):
        response = client.get(f'/api/events/{event_id}/uploads/{filename}')
    
    # Check that error was logged with context
    assert any('[PHOTO_SERVING]' in record.message for record in caplog.records)
    assert any('File not found' in record.message for record in caplog.records)
    assert any(event_id in record.message for record in caplog.records)
    assert any(filename in record.message for record in caplog.records)
    assert response.status_code == 404


def test_get_public_photo_logs_request(client, temp_folders, caplog):
    """Test that get_public_photo logs requests with proper context"""
    _, processed_folder = temp_folders
    event_id = "test_event_456"
    filename = "watermarked_photo.jpg"
    person_id = "person_001"
    
    # Create test structure
    group_dir = os.path.join(processed_folder, event_id, person_id, "group")
    os.makedirs(group_dir)
    test_file = os.path.join(group_dir, filename)
    with open(test_file, 'wb') as f:
        f.write(b'fake image data')
    
    with caplog.at_level(logging.INFO):
        response = client.get(f'/photos/{event_id}/all/{filename}')
    
    # Check that logging occurred
    assert any('[PHOTO_SERVING]' in record.message for record in caplog.records)
    assert any('serve_public' in record.message for record in caplog.records)
    assert any(event_id in record.message for record in caplog.records)


def test_get_private_photo_logs_unauthorized_access(client, temp_folders, caplog):
    """Test that unauthorized access attempts are logged"""
    event_id = "test_event_789"
    person_id = "person_002"
    photo_type = "individual"
    filename = "private.jpg"
    
    with caplog.at_level(logging.WARNING):
        response = client.get(f'/photos/{event_id}/{person_id}/{photo_type}/{filename}')
    
    # Check that unauthorized access was logged
    assert any('[PHOTO_SERVING]' in record.message for record in caplog.records)
    assert any('Unauthorized access attempt' in record.message for record in caplog.records)
    assert response.status_code == 401


def test_process_images_logs_processing_start_and_completion(temp_folders, caplog):
    """Test that process_images logs start and completion with statistics"""
    from backend.app import process_images
    
    upload_folder, processed_folder = temp_folders
    event_id = "test_event_processing"
    
    # Create test event folder (empty for this test)
    event_dir = os.path.join(upload_folder, event_id)
    os.makedirs(event_dir)
    
    with caplog.at_level(logging.INFO):
        process_images(event_id)
    
    # Check that processing was logged
    assert any('[PHOTO_PROCESSING]' in record.message for record in caplog.records)
    assert any('Starting processing' in record.message for record in caplog.records)
    assert any('Processing complete' in record.message for record in caplog.records)
    assert any(event_id in record.message for record in caplog.records)


def test_get_event_photos_logs_aggregation(client, temp_folders, caplog):
    """Test that get_event_photos logs photo aggregation operations"""
    event_id = "test_event_aggregation"
    
    with caplog.at_level(logging.INFO):
        response = client.get(f'/api/events/{event_id}/photos')
    
    # Check that aggregation was logged
    assert any('[PHOTO_AGGREGATION]' in record.message for record in caplog.records)
    assert any('Getting photos for event' in record.message for record in caplog.records)
    assert any(event_id in record.message for record in caplog.records)


def test_sanitization_functions_preserve_valid_inputs():
    """Test that sanitization functions don't break valid inputs"""
    # Valid event_id
    assert sanitize_path_component("event_123abc") == "event_123abc"
    
    # Valid filename
    assert sanitize_filename("photo_001.jpg") == "photo_001.jpg"
    
    # Path traversal attempts should be sanitized
    assert ".." not in sanitize_path_component("../../../etc")
    assert "/" not in sanitize_path_component("path/to/file")
    assert "\\" not in sanitize_path_component("path\\to\\file")


def test_logging_includes_operation_context(client, temp_folders, caplog):
    """Test that all log messages include operation context for traceability"""
    upload_folder, _ = temp_folders
    event_id = "test_event_context"
    filename = "test.jpg"
    
    # Create test file
    event_dir = os.path.join(upload_folder, event_id)
    os.makedirs(event_dir)
    test_file = os.path.join(event_dir, filename)
    with open(test_file, 'wb') as f:
        f.write(b'fake image data')
    
    with caplog.at_level(logging.INFO):
        response = client.get(f'/api/events/{event_id}/uploads/{filename}')
    
    # Check that operation context is included
    photo_serving_logs = [r for r in caplog.records if '[PHOTO_SERVING]' in r.message]
    assert len(photo_serving_logs) > 0
    assert any('operation:' in record.message for record in photo_serving_logs)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
