# Design Document

## Overview

This design addresses the photo display issue where uploaded photos don't appear on the event detail page until they've been processed. The solution adds a fallback mechanism to serve photos directly from the uploads folder when processed versions aren't available, while maintaining security and proper organization.

## Architecture

The system will use a layered approach:

1. **API Layer**: Enhanced `/api/events/<event_id>/photos` endpoint that aggregates photos from multiple sources
2. **File Serving Layer**: New `/api/events/<event_id>/uploads/<filename>` endpoint for serving original photos
3. **Frontend Layer**: Updated event detail page to handle photos from different sources

### Data Flow

```
User Request → Event Detail Page → API Endpoint → Photo Aggregation Logic
                                                    ↓
                                    ┌───────────────┴───────────────┐
                                    ↓                               ↓
                            Processed Folder                  Uploads Folder
                            (person_id/group/)                (original photos)
                                    ↓                               ↓
                            Watermarked Photos              Original Photos
                                    └───────────────┬───────────────┘
                                                    ↓
                                            Combined Photo List
                                            (deduplicated)
                                                    ↓
                                            Frontend Display
```

## Components and Interfaces

### 1. Photo Aggregation Service

**Purpose**: Collect photos from both processed and uploads folders

**Interface**:
```python
def get_event_photos_combined(event_id: str) -> dict:
    """
    Returns: {
        'success': bool,
        'photos': [
            {
                'url': str,
                'filename': str,
                'source': 'processed' | 'uploads',
                'type': 'group' | 'original'
            }
        ],
        'has_next': bool
    }
    """
```

**Logic**:
1. Scan processed folder for watermarked group photos ONLY (individual photos remain private)
2. Scan uploads folder for original photos (these are public until processed)
3. Deduplicate based on base filename (removing watermarked_ prefix)
4. Prioritize processed photos over originals
5. Return combined list with metadata

**Privacy Note**: 
- Individual photos in the processed folder remain hidden - they are only accessible via the biometric authentication flow
- Only group photos (watermarked_*) from the processed folder are shown publicly
- Original photos from uploads are shown publicly until processing completes
- Once processing completes, individual photos are hidden and only group photos are shown

### 2. Uploads Photo Serving Endpoint

**Purpose**: Serve photos directly from uploads folder

**Route**: `/api/events/<event_id>/uploads/<filename>`

**Security Measures**:
- Sanitize event_id using `sanitize_path_component()`
- Sanitize filename using `sanitize_filename()`
- Validate file exists within uploads folder
- Check file extension is in allowed list (.jpg, .jpeg, .png)
- Return 404 for invalid requests

**Implementation**:
```python
@app.route('/api/events/<event_id>/uploads/<filename>')
def serve_upload_photo(event_id, filename):
    # Sanitize inputs
    event_id = sanitize_path_component(event_id)
    filename = sanitize_filename(filename)
    
    # Validate extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png']:
        return "Invalid file type", 400
    
    # Build path and verify
    photo_path = os.path.join(app.config['UPLOAD_FOLDER'], event_id, filename)
    if not os.path.exists(photo_path):
        return "File Not Found", 404
    
    # Serve file
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], event_id),
        filename
    )
```

### 3. Enhanced Photo API Endpoint

**Purpose**: Update existing endpoint to include uploads folder photos

**Changes to `/api/events/<event_id>/photos`**:
- Add logic to scan uploads folder
- Combine with existing processed folder scan
- Deduplicate photos
- Add source metadata to response

### 4. Frontend Updates

**Purpose**: Handle photos from different sources

**Changes to event_detail.html**:
- No changes needed - the photo URLs will automatically point to the correct endpoint
- The existing image loading logic will work with both `/photos/...` and `/api/events/.../uploads/...` URLs

## Data Models

### Photo Metadata Structure

```javascript
{
    url: string,           // Full URL path to photo
    filename: string,      // Original filename
    source: string,        // 'processed' or 'uploads'
    type: string          // 'group', 'individual', or 'original'
}
```

### Photo List Response

```javascript
{
    success: boolean,
    photos: PhotoMetadata[],
    has_next: boolean,
    total_count: number
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Acceptance Criteria Testing Prework

1.1 WHEN photos are uploaded to an event THEN the Event System SHALL display those photos on the event detail page
Thoughts: This is about ensuring that after upload, photos become visible. We can test this by uploading photos to a random event, then querying the API and verifying the photos are in the response.
Testable: yes - property

1.2 WHEN the event detail page loads THEN the Event System SHALL check both uploads and processed folders for photos
Thoughts: This is about the system behavior of checking multiple sources. We can test by creating events with photos in different folders and verifying all are returned.
Testable: yes - property

1.3 WHEN displaying photos THEN the Event System SHALL show original photos from uploads if processed versions are not available
Thoughts: This is a fallback behavior. We can test by creating an event with only uploads folder photos and verifying they're returned.
Testable: yes - property

1.4 WHEN both original and processed versions exist THEN the Event System SHALL prioritize processed photos over originals
Thoughts: This is about deduplication priority. We can test by creating an event with the same photo in both folders and verifying only the processed version is returned.
Testable: yes - property

1.5 WHEN no photos exist in either folder THEN the Event System SHALL display a clear message indicating no photos are available
Thoughts: This is an edge case about empty state handling.
Testable: yes - example

2.1 WHEN the API endpoint receives a request for event photos THEN the Event System SHALL return photos from both processed and uploads folders
Thoughts: This is about the API combining multiple sources. We can test with random events that have photos in both locations.
Testable: yes - property

2.2 WHEN combining photos from multiple sources THEN the Event System SHALL remove duplicate photos based on filename
Thoughts: This is about deduplication logic. We can test by creating duplicate photos and verifying only one appears in results.
Testable: yes - property

2.3 WHEN returning photo URLs THEN the Event System SHALL provide correct paths that the browser can load
Thoughts: This is about URL correctness. We can test by verifying all returned URLs are valid and loadable.
Testable: yes - property

2.4 WHEN photos are in the uploads folder THEN the Event System SHALL serve them via a dedicated uploads endpoint
Thoughts: This is about routing. We can test by verifying uploads folder photos have URLs pointing to the uploads endpoint.
Testable: yes - property

2.5 WHEN the uploads folder contains non-photo files THEN the Event System SHALL filter to only image files with extensions .jpg, .jpeg, .png
Thoughts: This is about file filtering. We can test by adding non-image files and verifying they're excluded.
Testable: yes - property

3.1 WHEN serving photos from uploads folder THEN the Event System SHALL validate the event_id to prevent path traversal attacks
Thoughts: This is a security property. We can test with malicious event_ids containing path traversal attempts.
Testable: yes - property

3.2 WHEN serving photos from uploads folder THEN the Event System SHALL sanitize filenames to prevent directory traversal
Thoughts: This is a security property. We can test with malicious filenames.
Testable: yes - property

3.3 WHEN a photo request is made THEN the Event System SHALL verify the file exists before attempting to serve it
Thoughts: This is about error handling. We can test by requesting non-existent files.
Testable: yes - property

3.4 WHEN an invalid path is detected THEN the Event System SHALL return a 404 error
Thoughts: This is about error responses. We can test with invalid paths and verify the response code.
Testable: yes - property

3.5 WHEN serving files THEN the Event System SHALL only serve files from within the configured uploads directory
Thoughts: This is a security invariant. We can test by attempting to access files outside the uploads directory.
Testable: yes - property

4.1 WHEN the photo API is called THEN the Event System SHALL identify which photos are from uploads versus processed folders
Thoughts: This is about metadata accuracy. We can test by verifying the source field is correct for all photos.
Testable: yes - property

4.2 WHEN returning photo metadata THEN the Event System SHALL include the source folder for each photo
Thoughts: This is about response completeness. We can test by verifying all photos have a source field.
Testable: yes - property

4.3 WHEN displaying photos on the frontend THEN the Event System SHALL use appropriate endpoints based on photo source
Thoughts: This is about URL generation. We can test by verifying URLs match the photo source.
Testable: yes - property

4.4 WHEN processed photos become available THEN the Event System SHALL automatically prefer them over originals
Thoughts: This is the same as 1.4 - about deduplication priority.
Testable: yes - property (duplicate of 1.4)

4.5 WHEN the system serves a photo THEN the Event System SHALL use the correct MIME type based on file extension
Thoughts: This is about HTTP headers. We can test by verifying Content-Type headers match file extensions.
Testable: yes - property

### Property Reflection

After reviewing all properties, I've identified the following redundancies:

- Property 4.4 is logically equivalent to Property 1.4 (both test processed photo priority)
- Properties 2.1 and 1.2 overlap significantly (both test checking multiple folders)
- Properties 2.3 and 4.3 can be combined (both about URL correctness)

Consolidated properties:
- Combine 1.4 and 4.4 into a single comprehensive deduplication property
- Combine 1.2 and 2.1 into a single property about multi-source aggregation
- Combine 2.3 and 4.3 into a single property about URL generation

### Correctness Properties

Property 1: Photo visibility after upload
*For any* event with uploaded photos, querying the event photos API should return those photos in the response
**Validates: Requirements 1.1**

Property 2: Multi-source photo aggregation
*For any* event, the photo API should return photos from both uploads and processed folders when they exist
**Validates: Requirements 1.2, 2.1**

Property 3: Fallback to original photos
*For any* event with only uploads folder photos (no processed versions), the API should return those original photos
**Validates: Requirements 1.3**

Property 4: Processed photo priority and deduplication
*For any* event where the same photo exists in both uploads and processed folders, only the processed version should appear in the API response
**Validates: Requirements 1.4, 4.4**

Property 5: Filename-based deduplication
*For any* set of photos with matching base filenames (ignoring watermarked_ prefix), only one photo should appear in the results
**Validates: Requirements 2.2**

Property 6: URL correctness and routing
*For any* photo in the API response, the URL should correctly route to the appropriate endpoint based on the photo's source folder
**Validates: Requirements 2.3, 4.3**

Property 7: Uploads endpoint routing
*For any* photo from the uploads folder, the URL should use the `/api/events/<event_id>/uploads/<filename>` endpoint
**Validates: Requirements 2.4**

Property 8: Image file filtering
*For any* uploads folder containing mixed file types, only files with extensions .jpg, .jpeg, or .png should be included in results
**Validates: Requirements 2.5**

Property 9: Path traversal prevention for event_id
*For any* event_id containing path traversal characters (../, ..\, etc.), the system should sanitize or reject the request
**Validates: Requirements 3.1**

Property 10: Path traversal prevention for filename
*For any* filename containing path traversal characters, the system should sanitize or reject the request
**Validates: Requirements 3.2**

Property 11: File existence verification
*For any* photo request, if the file doesn't exist, the system should return a 404 error without attempting to serve
**Validates: Requirements 3.3**

Property 12: Invalid path error handling
*For any* request with an invalid or malicious path, the system should return a 404 error
**Validates: Requirements 3.4**

Property 13: Directory containment
*For any* file serving request, the resolved file path should be within the configured uploads directory
**Validates: Requirements 3.5**

Property 14: Source metadata accuracy
*For any* photo in the API response, the source field should correctly indicate whether it came from uploads or processed folder
**Validates: Requirements 4.1, 4.2**

Property 15: MIME type correctness
*For any* photo served, the Content-Type header should match the file extension (.jpg → image/jpeg, .png → image/png)
**Validates: Requirements 4.5**

## Error Handling

### File Not Found Errors
- Return 404 with clear message
- Log the attempted access for debugging
- Don't expose internal path structure

### Path Traversal Attempts
- Sanitize inputs before processing
- Return 404 (don't reveal security check)
- Log security events

### Empty Photo Lists
- Return success=true with empty photos array
- Include helpful message in response
- Frontend displays "No photos available" message

### File System Errors
- Catch and log exceptions
- Return 500 with generic error message
- Don't expose internal errors to client

## Testing Strategy

### Unit Testing

Unit tests will cover:
- Path sanitization functions with various malicious inputs
- Photo aggregation logic with different folder states
- Deduplication logic with various filename patterns
- URL generation for different photo sources
- File extension validation

### Property-Based Testing

We will use **pytest with Hypothesis** for property-based testing in Python.

Each property-based test will:
- Run a minimum of 100 iterations
- Generate random test data (event IDs, filenames, folder structures)
- Verify the correctness property holds across all inputs
- Be tagged with a comment referencing the design document property

Example test structure:
```python
from hypothesis import given, strategies as st

@given(
    event_id=st.text(min_size=1, max_size=50),
    filenames=st.lists(st.text(min_size=1, max_size=100))
)
def test_property_1_photo_visibility(event_id, filenames):
    """
    Feature: event-photo-display, Property 1: Photo visibility after upload
    Validates: Requirements 1.1
    """
    # Test implementation
```

### Integration Testing

Integration tests will verify:
- End-to-end photo upload and display flow
- API endpoint responses with real file system
- Frontend rendering with different photo sources
- Security measures with actual HTTP requests

## Implementation Notes

### Backward Compatibility
- Existing processed photo serving continues to work
- No changes to existing `/photos/<event_id>/all/<filename>` endpoint
- Frontend changes are additive only

### Performance Considerations
- File system scans should be cached where possible
- Consider pagination for events with many photos
- Lazy load images on frontend

### Security Considerations
- All path inputs must be sanitized
- File serving should use Flask's send_from_directory
- Never construct paths using string concatenation
- Validate file extensions before serving

### Privacy Considerations
- **Individual photos remain private**: Only accessible after biometric authentication
- **Group photos are public**: Watermarked group photos from processed folder are shown to all
- **Uploads are temporarily public**: Original photos in uploads folder are public until processing completes
- **Face matching without processing**: Users cannot retrieve their specific photos until processing completes and creates the person_id folders. The uploads folder shows ALL photos publicly.
- **Processing transition**: Once processing completes, the system automatically switches from showing uploads to showing only group photos, hiding individual photos

### Face Matching Limitation
The current design does NOT support retrieving matched photos before processing because:
1. Face matching requires the face recognition model to identify person_ids
2. Person_ids are only created during the processing step
3. The biometric authentication flow requires processed photos organized by person_id

If you need face matching on unprocessed photos, we would need to add:
- Real-time face recognition on uploads folder photos
- Temporary person_id assignment before full processing
- This would significantly increase complexity and processing time
