# Implementation Plan

- [x] 1. Add missing photo serving endpoint for uploads folder








  - Create `/api/events/<event_id>/uploads/<filename>` route in backend/app.py
  - Implement path sanitization for event_id and filename parameters
  - Use send_from_directory to serve files with correct MIME types
  - Return 404 with clear error message when file not found
  - Add error logging for file serving failures
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 1.1 Write property test for photo serving endpoint


  - **Property 1: Photo serving returns valid responses**
  - **Validates: Requirements 1.1, 1.3**

- [x] 1.2 Write property test for path sanitization


  - **Property 2: Path sanitization prevents traversal**
  - **Validates: Requirements 1.2**

- [x] 2. Fix photo aggregation logic





  - Update `scan_uploads_folder()` to use correct URL format with new endpoint
  - Verify `scan_processed_folder()` uses correct URL format
  - Review and fix `deduplicate_photos()` logic to properly strip watermarked prefix
  - Add logging to aggregation functions for debugging
  - Test aggregation with mixed processed/uploads scenarios
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 2.1 Write property test for deduplication logic


  - **Property 3: Deduplication prioritizes processed photos**
  - **Validates: Requirements 2.2, 2.3**

- [x] 2.2 Write property test for photo aggregation completeness



  - **Property 4: Photo aggregation includes all sources**
  - **Validates: Requirements 2.1, 2.4**

- [x] 3. Enhance photo processing reliability













  - Review `process_images()` function for error handling gaps
  - Add try-catch blocks around face detection operations
  - Add try-catch blocks around file copy operations
  - Ensure processing continues after individual photo failures
  - Add detailed logging for each processing step
  - Log face count and person IDs for each photo
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 3.1 Write property test for processing folder structure




  - **Property 5: Processing creates correct folder structure**
  - **Validates: Requirements 3.4, 3.5, 3.6**

- [x] 3.2 Write property test for error handling









  - **Property 6: Processing handles errors gracefully**
  - **Validates: Requirements 3.7, 4.4**

- [x] 4. Add comprehensive error logging





  - Add structured logging to all photo serving endpoints
  - Include event_id, filename, and operation in log messages
  - Log security violations (path traversal attempts)
  - Add error context to processing logs
  - Ensure all exceptions are logged before returning error responses
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 5. Test in Docker environment









  - Build Docker image with latest changes
  - Start container with volume mounts for uploads and processed folders
  - Upload test photos and verify processing occurs
  - Check that photos are accessible via both endpoints
  - Verify no 404 errors in browser console
  - Test with multiple events and photo uploads
  - _Requirements: 3.1, 3.7_

- [x] 6. Checkpoint - Verify all functionality




  - Ensure all tests pass, ask the user if questions arise.
