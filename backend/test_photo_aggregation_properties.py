"""
Property-based tests for photo aggregation logic.
Uses Hypothesis to test correctness properties across many inputs.

Feature: photo-serving-fix
"""
import pytest
from hypothesis import given, strategies as st, settings
from backend.app import deduplicate_photos, scan_uploads_folder, scan_processed_folder
import os
import shutil
import tempfile
import string


# --- GENERATORS FOR PROPERTY-BASED TESTING ---

@st.composite
def photo_metadata(draw, source_type='uploads'):
    """
    Generate a photo metadata dictionary.
    
    Args:
        source_type: 'uploads' or 'processed'
    """
    # Generate a base filename
    base_name = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), min_codepoint=48, max_codepoint=122),
        min_size=1,
        max_size=20
    ))
    extension = draw(st.sampled_from(['.jpg', '.jpeg', '.png']))
    
    if source_type == 'processed':
        filename = f"watermarked_{base_name}{extension}"
        url = f"/photos/event_test/all/{filename}"
        photo_type = 'group'
    else:
        filename = f"{base_name}{extension}"
        url = f"/api/events/event_test/uploads/{filename}"
        photo_type = 'original'
    
    return {
        'filename': filename,
        'source': source_type,
        'type': photo_type,
        'url': url
    }


@st.composite
def photo_lists_with_duplicates(draw):
    """
    Generate processed and uploads photo lists where some photos are duplicates.
    
    Returns a tuple: (processed_photos, uploads_photos, expected_duplicate_count)
    """
    # Generate some base filenames that will be duplicated
    num_duplicates = draw(st.integers(min_value=0, max_value=5))
    num_processed_only = draw(st.integers(min_value=0, max_value=5))
    num_uploads_only = draw(st.integers(min_value=0, max_value=5))
    
    processed_photos = []
    uploads_photos = []
    
    # Create duplicate photos (exist in both processed and uploads)
    for i in range(num_duplicates):
        base_name = f"duplicate_{i}"
        extension = '.jpg'
        
        # Add to processed with watermarked_ prefix
        processed_photos.append({
            'filename': f"watermarked_{base_name}{extension}",
            'source': 'processed',
            'type': 'group',
            'url': f"/photos/event_test/all/watermarked_{base_name}{extension}"
        })
        
        # Add to uploads without prefix
        uploads_photos.append({
            'filename': f"{base_name}{extension}",
            'source': 'uploads',
            'type': 'original',
            'url': f"/api/events/event_test/uploads/{base_name}{extension}"
        })
    
    # Add processed-only photos
    for i in range(num_processed_only):
        base_name = f"processed_only_{i}"
        extension = '.jpg'
        processed_photos.append({
            'filename': f"watermarked_{base_name}{extension}",
            'source': 'processed',
            'type': 'group',
            'url': f"/photos/event_test/all/watermarked_{base_name}{extension}"
        })
    
    # Add uploads-only photos
    for i in range(num_uploads_only):
        base_name = f"uploads_only_{i}"
        extension = '.jpg'
        uploads_photos.append({
            'filename': f"{base_name}{extension}",
            'source': 'uploads',
            'type': 'original',
            'url': f"/api/events/event_test/uploads/{base_name}{extension}"
        })
    
    return processed_photos, uploads_photos, num_duplicates


# --- PROPERTY-BASED TESTS ---

@given(photo_lists_with_duplicates())
@settings(max_examples=100)
def test_property_deduplication_prioritizes_processed(photo_data):
    """
    Feature: photo-serving-fix, Property 3: Deduplication prioritizes processed photos
    Validates: Requirements 2.2, 2.3
    
    Property: For any set of photos where a processed version exists (with watermarked_ prefix),
    the deduplicated result should contain only the processed version and exclude the original
    from uploads.
    
    This test verifies that:
    1. When a photo exists in both processed and uploads, only the processed version appears
    2. The deduplicated list has the correct total count
    3. No duplicate base filenames exist in the result
    """
    processed_photos, uploads_photos, num_duplicates = photo_data
    
    # Run deduplication
    result = deduplicate_photos(processed_photos, uploads_photos)
    
    # Property 1: All processed photos should be in the result
    for processed_photo in processed_photos:
        assert processed_photo in result, \
            f"Processed photo {processed_photo['filename']} should be in result"
    
    # Property 2: For each duplicate, the uploads version should NOT be in result
    for processed_photo in processed_photos:
        if processed_photo['filename'].startswith('watermarked_'):
            base_name = processed_photo['filename'][len('watermarked_'):]
            
            # Check if this base_name exists in uploads
            matching_uploads = [p for p in uploads_photos if p['filename'] == base_name]
            
            if matching_uploads:
                # The uploads version should NOT be in the result
                for upload_photo in matching_uploads:
                    assert upload_photo not in result, \
                        f"Upload photo {upload_photo['filename']} should be excluded when processed version exists"
    
    # Property 3: Result should have correct total count
    # Total = all processed + uploads that don't have processed versions
    expected_count = len(processed_photos) + len(uploads_photos) - num_duplicates
    assert len(result) == expected_count, \
        f"Expected {expected_count} photos, got {len(result)}"
    
    # Property 4: No duplicate base filenames in result
    base_filenames = []
    for photo in result:
        filename = photo['filename']
        if filename.startswith('watermarked_'):
            base_name = filename[len('watermarked_'):]
        else:
            base_name = filename
        base_filenames.append(base_name)
    
    # Check for duplicates
    assert len(base_filenames) == len(set(base_filenames)), \
        f"Result contains duplicate base filenames: {base_filenames}"


@given(
    st.lists(photo_metadata(source_type='processed'), min_size=0, max_size=10),
    st.lists(photo_metadata(source_type='uploads'), min_size=0, max_size=10)
)
@settings(max_examples=100)
def test_property_deduplication_preserves_all_unique_photos(processed_photos, uploads_photos):
    """
    Feature: photo-serving-fix, Property 3: Deduplication prioritizes processed photos
    Validates: Requirements 2.2, 2.3
    
    Property: Deduplication should preserve all unique photos (those that don't have
    duplicates in the other list).
    
    This test verifies that photos appearing in only one list are always included
    in the result.
    """
    result = deduplicate_photos(processed_photos, uploads_photos)
    
    # Build set of base filenames from processed
    processed_base_names = set()
    for photo in processed_photos:
        filename = photo['filename']
        if filename.startswith('watermarked_'):
            base_name = filename[len('watermarked_'):]
        else:
            base_name = filename
        processed_base_names.add(base_name)
    
    # All processed photos should be in result
    for photo in processed_photos:
        assert photo in result, \
            f"Processed photo {photo['filename']} should always be in result"
    
    # Uploads photos should be in result only if they don't have a processed version
    for photo in uploads_photos:
        if photo['filename'] not in processed_base_names:
            assert photo in result, \
                f"Unique upload photo {photo['filename']} should be in result"
        else:
            assert photo not in result, \
                f"Upload photo {photo['filename']} should be excluded (has processed version)"


@given(st.lists(photo_metadata(source_type='processed'), min_size=1, max_size=10))
@settings(max_examples=100)
def test_property_deduplication_with_empty_uploads(processed_photos):
    """
    Feature: photo-serving-fix, Property 3: Deduplication prioritizes processed photos
    Validates: Requirements 2.2, 2.3
    
    Property: When uploads list is empty, all processed photos should be returned.
    """
    result = deduplicate_photos(processed_photos, [])
    
    assert len(result) == len(processed_photos), \
        "All processed photos should be in result when uploads is empty"
    
    for photo in processed_photos:
        assert photo in result, \
            f"Processed photo {photo['filename']} should be in result"


@given(st.lists(photo_metadata(source_type='uploads'), min_size=1, max_size=10))
@settings(max_examples=100)
def test_property_deduplication_with_empty_processed(uploads_photos):
    """
    Feature: photo-serving-fix, Property 3: Deduplication prioritizes processed photos
    Validates: Requirements 2.2, 2.3
    
    Property: When processed list is empty, all uploads photos should be returned.
    """
    result = deduplicate_photos([], uploads_photos)
    
    assert len(result) == len(uploads_photos), \
        "All uploads photos should be in result when processed is empty"
    
    for photo in uploads_photos:
        assert photo in result, \
            f"Upload photo {photo['filename']} should be in result"



# --- PROPERTY TESTS FOR PHOTO AGGREGATION COMPLETENESS ---

@st.composite
def event_folder_structure(draw):
    """
    Generate a realistic event folder structure with photos in both uploads and processed.
    
    Returns: (event_id, uploads_files, processed_files_by_person)
    """
    event_id = f"event_{draw(st.text(alphabet=st.characters(whitelist_categories=('Ll', 'Nd')), min_size=4, max_size=8))}"
    
    # Generate uploads files
    num_uploads = draw(st.integers(min_value=0, max_value=10))
    uploads_files = []
    for i in range(num_uploads):
        filename = f"photo_{i}.jpg"
        uploads_files.append(filename)
    
    # Generate processed files (organized by person)
    num_persons = draw(st.integers(min_value=0, max_value=5))
    processed_files_by_person = {}
    
    for person_idx in range(num_persons):
        person_id = f"person_{person_idx:03d}"
        num_group_photos = draw(st.integers(min_value=0, max_value=5))
        
        group_photos = []
        for photo_idx in range(num_group_photos):
            filename = f"watermarked_group_{person_idx}_{photo_idx}.jpg"
            group_photos.append(filename)
        
        if group_photos:
            processed_files_by_person[person_id] = group_photos
    
    return event_id, uploads_files, processed_files_by_person


def create_test_event_structure(base_dir, event_id, uploads_files, processed_files_by_person):
    """
    Create actual folder structure for testing scan functions.
    
    Args:
        base_dir: Base directory for uploads/processed folders
        event_id: Event identifier
        uploads_files: List of filenames for uploads folder
        processed_files_by_person: Dict mapping person_id to list of group photo filenames
    
    Returns:
        Tuple of (uploads_dir, processed_dir)
    """
    # Create uploads folder
    uploads_dir = os.path.join(base_dir, 'uploads', event_id)
    os.makedirs(uploads_dir, exist_ok=True)
    
    for filename in uploads_files:
        filepath = os.path.join(uploads_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(b'fake image data')
    
    # Create processed folder structure
    processed_dir = os.path.join(base_dir, 'processed', event_id)
    
    for person_id, group_photos in processed_files_by_person.items():
        group_dir = os.path.join(processed_dir, person_id, 'group')
        os.makedirs(group_dir, exist_ok=True)
        
        for filename in group_photos:
            filepath = os.path.join(group_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(b'fake watermarked data')
    
    return uploads_dir, processed_dir


@given(event_folder_structure())
@settings(max_examples=100, deadline=None)
def test_property_aggregation_includes_all_sources(event_data):
    """
    Feature: photo-serving-fix, Property 4: Photo aggregation includes all sources
    Validates: Requirements 2.1, 2.4
    
    Property: For any event, the aggregated photo list should include photos from both
    processed and uploads folders, with no photos missing from either source (after deduplication).
    
    This test verifies that:
    1. All photos from uploads folder are scanned
    2. All photos from processed folder are scanned
    3. The aggregation includes photos from both sources
    4. No photos are lost during aggregation
    """
    event_id, uploads_files, processed_files_by_person = event_data
    
    # Create temporary directory structure
    with tempfile.TemporaryDirectory() as tmpdir:
        # Temporarily override app config
        from backend import app as flask_app
        original_upload_folder = flask_app.app.config['UPLOAD_FOLDER']
        original_processed_folder = flask_app.app.config['PROCESSED_FOLDER']
        
        try:
            flask_app.app.config['UPLOAD_FOLDER'] = os.path.join(tmpdir, 'uploads')
            flask_app.app.config['PROCESSED_FOLDER'] = os.path.join(tmpdir, 'processed')
            
            # Create the folder structure
            uploads_dir, processed_dir = create_test_event_structure(
                tmpdir, event_id, uploads_files, processed_files_by_person
            )
            
            # Scan both folders
            uploads_photos = scan_uploads_folder(event_id)
            processed_photos = scan_processed_folder(event_id)
            
            # Property 1: All uploads files should be scanned
            scanned_upload_filenames = {p['filename'] for p in uploads_photos}
            expected_upload_filenames = set(uploads_files)
            assert scanned_upload_filenames == expected_upload_filenames, \
                f"Missing uploads: {expected_upload_filenames - scanned_upload_filenames}"
            
            # Property 2: All processed files should be scanned
            scanned_processed_filenames = {p['filename'] for p in processed_photos}
            expected_processed_filenames = set()
            for group_photos in processed_files_by_person.values():
                expected_processed_filenames.update(group_photos)
            
            assert scanned_processed_filenames == expected_processed_filenames, \
                f"Missing processed: {expected_processed_filenames - scanned_processed_filenames}"
            
            # Property 3: Deduplicated aggregation should include all unique photos
            aggregated = deduplicate_photos(processed_photos, uploads_photos)
            
            # Count expected photos after deduplication
            # All processed photos + uploads that don't have processed versions
            processed_base_names = set()
            for photo in processed_photos:
                filename = photo['filename']
                if filename.startswith('watermarked_'):
                    base_name = filename[len('watermarked_'):]
                else:
                    base_name = filename
                processed_base_names.add(base_name)
            
            expected_count = len(processed_photos)
            for upload_file in uploads_files:
                if upload_file not in processed_base_names:
                    expected_count += 1
            
            assert len(aggregated) == expected_count, \
                f"Expected {expected_count} photos in aggregation, got {len(aggregated)}"
            
            # Property 4: All processed photos should be in aggregation
            for photo in processed_photos:
                assert photo in aggregated, \
                    f"Processed photo {photo['filename']} missing from aggregation"
            
            # Property 5: Uploads without processed versions should be in aggregation
            for photo in uploads_photos:
                if photo['filename'] not in processed_base_names:
                    assert photo in aggregated, \
                        f"Unique upload photo {photo['filename']} missing from aggregation"
        
        finally:
            # Restore original config
            flask_app.app.config['UPLOAD_FOLDER'] = original_upload_folder
            flask_app.app.config['PROCESSED_FOLDER'] = original_processed_folder


@given(
    st.integers(min_value=0, max_value=20),
    st.integers(min_value=0, max_value=20)
)
@settings(max_examples=100, deadline=None)
def test_property_scan_functions_return_correct_count(num_uploads, num_processed):
    """
    Feature: photo-serving-fix, Property 4: Photo aggregation includes all sources
    Validates: Requirements 2.1, 2.4
    
    Property: The scan functions should return exactly the number of valid image files
    in their respective folders.
    """
    event_id = "test_event_count"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        from backend import app as flask_app
        original_upload_folder = flask_app.app.config['UPLOAD_FOLDER']
        original_processed_folder = flask_app.app.config['PROCESSED_FOLDER']
        
        try:
            flask_app.app.config['UPLOAD_FOLDER'] = os.path.join(tmpdir, 'uploads')
            flask_app.app.config['PROCESSED_FOLDER'] = os.path.join(tmpdir, 'processed')
            
            # Create uploads
            uploads_dir = os.path.join(tmpdir, 'uploads', event_id)
            os.makedirs(uploads_dir, exist_ok=True)
            
            for i in range(num_uploads):
                filepath = os.path.join(uploads_dir, f"photo_{i}.jpg")
                with open(filepath, 'wb') as f:
                    f.write(b'fake image')
            
            # Create processed
            processed_dir = os.path.join(tmpdir, 'processed', event_id, 'person_001', 'group')
            os.makedirs(processed_dir, exist_ok=True)
            
            for i in range(num_processed):
                filepath = os.path.join(processed_dir, f"watermarked_photo_{i}.jpg")
                with open(filepath, 'wb') as f:
                    f.write(b'fake watermarked')
            
            # Scan and verify counts
            uploads_photos = scan_uploads_folder(event_id)
            processed_photos = scan_processed_folder(event_id)
            
            assert len(uploads_photos) == num_uploads, \
                f"Expected {num_uploads} uploads, got {len(uploads_photos)}"
            
            assert len(processed_photos) == num_processed, \
                f"Expected {num_processed} processed, got {len(processed_photos)}"
        
        finally:
            flask_app.app.config['UPLOAD_FOLDER'] = original_upload_folder
            flask_app.app.config['PROCESSED_FOLDER'] = original_processed_folder


@given(st.lists(
    st.text(
        alphabet=string.ascii_letters + string.digits,  # Use ASCII only to avoid Unicode case issues
        min_size=1, 
        max_size=15
    ), 
    min_size=1, 
    max_size=10, 
    unique=True
))
@settings(max_examples=100, deadline=None)
def test_property_scan_uploads_filters_qr_codes(filenames):
    """
    Feature: photo-serving-fix, Property 4: Photo aggregation includes all sources
    Validates: Requirements 2.1, 2.4
    
    Property: The scan_uploads_folder function should filter out QR code files
    (files ending with _qr.png).
    """
    event_id = "test_event_qr_filter"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        from backend import app as flask_app
        original_upload_folder = flask_app.app.config['UPLOAD_FOLDER']
        
        try:
            flask_app.app.config['UPLOAD_FOLDER'] = os.path.join(tmpdir, 'uploads')
            
            uploads_dir = os.path.join(tmpdir, 'uploads', event_id)
            os.makedirs(uploads_dir, exist_ok=True)
            
            # Create regular photos (filenames are unique)
            created_files = []
            for filename in filenames:
                filepath = os.path.join(uploads_dir, f"{filename}.jpg")
                with open(filepath, 'wb') as f:
                    f.write(b'fake image')
                # Verify file was actually created
                if os.path.exists(filepath):
                    created_files.append(filename)
            
            regular_count = len(created_files)
            
            # Create QR code (should be filtered)
            qr_filepath = os.path.join(uploads_dir, f"{event_id}_qr.png")
            with open(qr_filepath, 'wb') as f:
                f.write(b'fake qr')
            
            # Scan
            photos = scan_uploads_folder(event_id)
            
            # Property: Should have only regular photos, not QR code
            assert len(photos) == regular_count, \
                f"Expected {regular_count} photos (QR filtered), got {len(photos)}. Created files: {created_files}, Photos: {[p['filename'] for p in photos]}"
            
            # Verify no QR code in results
            for photo in photos:
                assert not photo['filename'].endswith('_qr.png'), \
                    f"QR code should be filtered: {photo['filename']}"
        
        finally:
            flask_app.app.config['UPLOAD_FOLDER'] = original_upload_folder
