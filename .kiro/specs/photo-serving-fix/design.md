# Design Document

## Overview

This design addresses critical photo serving and processing issues in the PicMe application. The solution involves adding a missing API endpoint for serving uploaded photos, fixing the photo aggregation logic, and ensuring proper photo processing in Docker environments. The design focuses on reliability, security, and proper error handling.

## Architecture

The photo serving architecture consists of three main components:

1. **Photo Serving Layer**: HTTP endpoints that serve photos from different sources (uploads and processed folders)
2. **Photo Aggregation Layer**: Logic that combines photos from multiple sources and deduplicates them
3. **Photo Processing Layer**: Background thread that performs face recognition and categorizes photos

### Data Flow

```
Upload → Uploads Folder → Processing Thread → Face Recognition → Processed Folder
                ↓                                                        ↓
         Serve via /api/events/{id}/uploads/          Serve via /photos/{id}/all/
                ↓                                                        ↓
                        Photo Aggregation API
                                ↓
                        Event Gallery Display
```

## Components and Interfaces

### 1. Photo Serving Endpoints

#### `/api/events/<event_id>/uploads/<filename>` (NEW)
- **Method**: GET
- **Purpose**: Serve original photos from the uploads folder
- **Authentication**: Public access (no login required)
- **Parameters**:
  - `event_id`: Event identifier (sanitized)
  - `filename`: Photo filename (sanitized)
- **Returns**: Photo file with appropriate MIME type or 404
- **Security**: Path sanitization to prevent directory traversal

#### `/photos/<event_id>/all/<filename>` (EXISTING)
- **Method**: GET
- **Purpose**: Serve processed group photos
- **Authentication**: Public access
- **Parameters**:
  - `event_id`: Event identifier (sanitized)
  - `filename`: Photo filename (sanitized, must start with `watermarked_`)
- **Returns**: Photo file or 404

### 2. Photo Aggregation Functions

#### `scan_uploads_folder(event_id)`
- **Purpose**: Scan uploads folder for original photos
- **Returns**: List of photo metadata dicts with keys: filename, source, type, url
- **URL Format**: `/api/events/{event_id}/uploads/{filename}`
- **Filters**: Excludes QR codes, only includes .jpg, .jpeg, .png

#### `scan_processed_folder(event_id)`
- **Purpose**: Scan processed folder for group photos
- **Returns**: List of photo metadata dicts
- **URL Format**: `/photos/{event_id}/all/{filename}`
- **Filters**: Only includes watermarked group photos

#### `deduplicate_photos(processed_photos, uploads_photos)`
- **Purpose**: Remove duplicates, prioritizing processed over originals
- **Logic**: 
  - Extract base filename from processed photos (strip `watermarked_` prefix)
  - Filter uploads to exclude any with matching base filenames
  - Return combined list: processed + filtered uploads

### 3. Photo Processing

#### `process_images(event_id)`
- **Purpose**: Background thread that processes uploaded photos
- **Steps**:
  1. Scan uploads folder for new photos
  2. For each photo:
     - Load image and detect faces
     - Learn/update face encodings
     - Categorize as individual (1 face) or group (multiple faces)
     - Copy to appropriate processed folder structure
  3. Log progress and errors
- **Folder Structure**:
  ```
  processed/
    event_id/
      person_id/
        individual/
          photo.jpg
        group/
          watermarked_photo.jpg
  ```

## Data Models

### Photo Metadata
```python
{
    'filename': str,      # Original filename
    'source': str,        # 'uploads' or 'processed'
    'type': str,          # 'original' or 'group'
    'url': str            # Full URL path to photo
}
```

### Photo Aggregation Response
```python
{
    'success': bool,
    'photos': [str],      # List of photo URLs
    'has_next': bool,     # Pagination flag
    'message': str        # Optional message for empty case
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Photo serving returns valid responses
*For any* valid event_id and filename combination that exists in the uploads folder, requesting the photo via `/api/events/{event_id}/uploads/{filename}` should return a 200 status code with the photo file content.
**Validates: Requirements 1.1, 1.3**

### Property 2: Path sanitization prevents traversal
*For any* event_id or filename containing path traversal characters (../, ..\, /, \), the system should sanitize them before file system operations, preventing access to files outside the intended directories.
**Validates: Requirements 1.2**

### Property 3: Deduplication prioritizes processed photos
*For any* set of photos where a processed version exists (with `watermarked_` prefix), the deduplicated result should contain only the processed version and exclude the original from uploads.
**Validates: Requirements 2.2, 2.3**

### Property 4: Photo aggregation includes all sources
*For any* event, the aggregated photo list should include photos from both processed and uploads folders, with no photos missing from either source (after deduplication).
**Validates: Requirements 2.1, 2.4**

### Property 5: Processing creates correct folder structure
*For any* uploaded photo with detected faces, after processing completes, the processed folder should contain the photo in the appropriate person_id/individual or person_id/group subfolder.
**Validates: Requirements 3.4, 3.5, 3.6**

### Property 6: Processing handles errors gracefully
*For any* photo that fails to process (corrupt file, no faces, etc.), the processing thread should log the error and continue processing remaining photos without crashing.
**Validates: Requirements 3.7, 4.4**

## Error Handling

### Photo Serving Errors
- **404 Not Found**: Photo file doesn't exist at the specified path
- **400 Bad Request**: Invalid event_id or filename (after sanitization results in empty string)
- **500 Internal Server Error**: File system error or unexpected exception

### Processing Errors
- **Face Detection Failure**: Log warning, skip photo, continue processing
- **File I/O Error**: Log error with file path, continue processing
- **Model Error**: Log error, skip photo, continue processing

### Logging Strategy
- **INFO**: Processing start/completion, photo counts
- **WARNING**: Skipped photos, missing folders
- **ERROR**: File I/O failures, model errors, unexpected exceptions
- **Context**: Always include event_id, filename, and operation type

## Testing Strategy

### Unit Testing
- Test path sanitization with various malicious inputs
- Test deduplication logic with different photo combinations
- Test photo metadata extraction from filenames
- Test error handling for missing files and folders

### Property-Based Testing
We will use **Hypothesis** (Python's property-based testing library) for this project.

Each property-based test should run a minimum of 100 iterations to ensure thorough coverage of the input space.

Property-based tests must be tagged with comments explicitly referencing the correctness property from this design document using the format: `# Feature: photo-serving-fix, Property {number}: {property_text}`

Each correctness property will be implemented by a single property-based test.

### Integration Testing
- Test full photo upload → processing → serving workflow
- Test photo aggregation API with real folder structures
- Test concurrent photo uploads and processing
- Test Docker environment with volume mounts

### Manual Testing
- Upload photos and verify they appear in event gallery
- Verify processed photos display correctly
- Verify original photos display when processing incomplete
- Check browser console for 404 errors
