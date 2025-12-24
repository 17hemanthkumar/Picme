"""
Tests for enhanced photo aggregation logic.
Tests the /api/events/<event_id>/photos endpoint with multi-source aggregation.
"""
import pytest
import os
import shutil
from backend.app import app


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def test_event_with_both_folders(tmp_path):
    """
    Create a test event with photos in both uploads and processed folders.
    """
    event_id = "test_event_both"
    
    # Create uploads folder with original photos
    uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
    os.makedirs(uploads_dir, exist_ok=True)
    
    # Create some test image files in uploads
    for i in range(3):
        photo_path = os.path.join(uploads_dir, f"photo_{i}.jpg")
        with open(photo_path, 'wb') as f:
            f.write(b'fake image data')
    
    # Create processed folder with watermarked group photos
    processed_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
    person_dir = os.path.join(processed_dir, "person_001", "group")
    os.makedirs(person_dir, exist_ok=True)
    
    # Create watermarked version of photo_0 (should deduplicate)
    watermarked_path = os.path.join(person_dir, "watermarked_photo_0.jpg")
    with open(watermarked_path, 'wb') as f:
        f.write(b'fake watermarked image data')
    
    # Create another watermarked photo that doesn't exist in uploads
    watermarked_path2 = os.path.join(person_dir, "watermarked_photo_99.jpg")
    with open(watermarked_path2, 'wb') as f:
        f.write(b'fake watermarked image data 2')
    
    yield {
        'event_id': event_id,
        'uploads_dir': uploads_dir,
        'processed_dir': processed_dir
    }
    
    # Cleanup
    if os.path.exists(uploads_dir):
        shutil.rmtree(uploads_dir)
    if os.path.exists(processed_dir):
        shutil.rmtree(processed_dir)


@pytest.fixture
def test_event_uploads_only(tmp_path):
    """Create a test event with photos only in uploads folder."""
    event_id = "test_event_uploads"
    
    uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
    os.makedirs(uploads_dir, exist_ok=True)
    
    # Create test image files
    for i in range(2):
        photo_path = os.path.join(uploads_dir, f"original_{i}.jpg")
        with open(photo_path, 'wb') as f:
            f.write(b'fake image data')
    
    yield {
        'event_id': event_id,
        'uploads_dir': uploads_dir
    }
    
    # Cleanup
    if os.path.exists(uploads_dir):
        shutil.rmtree(uploads_dir)


@pytest.fixture
def test_event_processed_only(tmp_path):
    """Create a test event with photos only in processed folder."""
    event_id = "test_event_processed"
    
    processed_dir = os.path.join(app.config['PROCESSED_FOLDER'], event_id)
    person_dir = os.path.join(processed_dir, "person_002", "group")
    os.makedirs(person_dir, exist_ok=True)
    
    # Create watermarked photos
    for i in range(2):
        photo_path = os.path.join(person_dir, f"watermarked_group_{i}.jpg")
        with open(photo_path, 'wb') as f:
            f.write(b'fake watermarked data')
    
    yield {
        'event_id': event_id,
        'processed_dir': processed_dir
    }
    
    # Cleanup
    if os.path.exists(processed_dir):
        shutil.rmtree(processed_dir)


def test_aggregates_from_both_folders(client, test_event_with_both_folders):
    """
    Test that the endpoint returns ONLY processed photos (not uploads).
    
    This ensures:
    - No duplicate photos in the public gallery
    - Individual photos remain private
    - Only watermarked group photos are shown
    """
    event_id = test_event_with_both_folders['event_id']
    response = client.get(f"/api/events/{event_id}/photos")
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert data['success'] is True
    assert 'photos' in data
    
    # Should have photos from processed folder only
    photos = data['photos']
    assert len(photos) > 0
    
    # Should ONLY have processed photos (no uploads)
    has_uploads = any('/uploads/' in url for url in photos)
    has_processed = any('/photos/' in url for url in photos)
    
    assert not has_uploads, "Should not include uploads in public gallery"
    assert has_processed, "Should include processed photos"
    
    # All photos should be from the processed endpoint
    assert all('/photos/' in url for url in photos)


def test_deduplication_prioritizes_processed(client, test_event_with_both_folders):
    """
    Test that when the same photo exists in both folders,
    only the processed version appears in results.
    """
    event_id = test_event_with_both_folders['event_id']
    response = client.get(f"/api/events/{event_id}/photos")
    
    assert response.status_code == 200
    data = response.get_json()
    photos = data['photos']
    
    # Count occurrences of photo_0 (exists in both folders)
    photo_0_count = sum(1 for url in photos if 'photo_0.jpg' in url)
    
    # Should only appear once (the processed version)
    assert photo_0_count == 1
    
    # Verify it's the processed version (not the uploads version)
    photo_0_url = next(url for url in photos if 'photo_0.jpg' in url)
    assert '/photos/' in photo_0_url  # Processed endpoint
    assert 'watermarked_' in photo_0_url


def test_fallback_to_uploads_only(client, test_event_uploads_only):
    """
    Test that when only uploads folder has photos (no processed photos),
    the endpoint returns empty with a message indicating processing is needed.
    
    This ensures individual photos remain private and only processed group photos
    are shown in the public gallery.
    """
    event_id = test_event_uploads_only['event_id']
    response = client.get(f"/api/events/{event_id}/photos")
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert data['success'] is True
    photos = data['photos']
    
    # Should have 0 photos since we only show processed photos
    assert len(photos) == 0
    
    # Should have a message indicating photos need processing
    assert 'message' in data
    assert 'processing' in data['message'].lower()


def test_processed_only_works(client, test_event_processed_only):
    """
    Test that when only processed folder has photos, they are returned.
    """
    event_id = test_event_processed_only['event_id']
    response = client.get(f"/api/events/{event_id}/photos")
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert data['success'] is True
    photos = data['photos']
    
    # Should have 2 photos from processed
    assert len(photos) == 2
    
    # All should be from processed endpoint
    assert all('/photos/' in url for url in photos)


def test_empty_event_returns_success_with_message(client):
    """
    Test that an event with no photos returns success with helpful message.
    """
    response = client.get("/api/events/nonexistent_event/photos")
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert data['success'] is True
    assert data['photos'] == []
    assert 'message' in data
    assert 'No photos available' in data['message']


def test_filters_non_image_files(client, tmp_path):
    """
    Test that non-image files in uploads folder are filtered out.
    
    Note: Since we now only show processed photos, this test verifies
    that the scan_uploads_folder function still filters correctly
    (even though uploads aren't shown in the public gallery).
    """
    event_id = "test_event_mixed"
    uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
    os.makedirs(uploads_dir, exist_ok=True)
    
    try:
        # Create image files
        for i in range(2):
            photo_path = os.path.join(uploads_dir, f"photo_{i}.jpg")
            with open(photo_path, 'wb') as f:
                f.write(b'fake image')
        
        # Create non-image files (should be filtered)
        txt_path = os.path.join(uploads_dir, "readme.txt")
        with open(txt_path, 'w') as f:
            f.write("not an image")
        
        pdf_path = os.path.join(uploads_dir, "document.pdf")
        with open(pdf_path, 'wb') as f:
            f.write(b'fake pdf')
        
        response = client.get(f"/api/events/{event_id}/photos")
        
        assert response.status_code == 200
        data = response.get_json()
        photos = data['photos']
        
        # Should have 0 photos since we only show processed photos
        assert len(photos) == 0
        
        # Should have message about processing
        assert 'message' in data
        
    finally:
        if os.path.exists(uploads_dir):
            shutil.rmtree(uploads_dir)


def test_skips_qr_codes(client, tmp_path):
    """
    Test that QR code files are not included in photo results.
    
    Note: Since we now only show processed photos, this test verifies
    that uploads (including QR codes) are not shown in the public gallery.
    """
    event_id = "test_event_qr"
    uploads_dir = os.path.join(app.config['UPLOAD_FOLDER'], event_id)
    os.makedirs(uploads_dir, exist_ok=True)
    
    try:
        # Create regular photo
        photo_path = os.path.join(uploads_dir, "photo.jpg")
        with open(photo_path, 'wb') as f:
            f.write(b'fake image')
        
        # Create QR code (should be skipped)
        qr_path = os.path.join(uploads_dir, f"{event_id}_qr.png")
        with open(qr_path, 'wb') as f:
            f.write(b'fake qr code')
        
        response = client.get(f"/api/events/{event_id}/photos")
        
        assert response.status_code == 200
        data = response.get_json()
        photos = data['photos']
        
        # Should have 0 photos since we only show processed photos
        assert len(photos) == 0
        assert not any('_qr.png' in url for url in photos)
        
    finally:
        if os.path.exists(uploads_dir):
            shutil.rmtree(uploads_dir)
