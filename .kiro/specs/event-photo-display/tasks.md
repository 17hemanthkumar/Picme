# Implementation Plan

- [x] 1. Create uploads photo serving endpoint





  - Add new route `/api/events/<event_id>/uploads/<filename>` to serve photos from uploads folder
  - Implement path sanitization for event_id and filename using existing security functions
  - Validate file extension is in allowed list (.jpg, .jpeg, .png)
  - Verify file exists before serving
  - Use Flask's send_from_directory for secure file serving
  - Return 404 for invalid requests
  - _Requirements: 2.4, 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ]* 1.1 Write property test for path traversal prevention
  - **Property 9: Path traversal prevention for event_id**
  - **Validates: Requirements 3.1**

- [ ]* 1.2 Write property test for filename sanitization
  - **Property 10: Path traversal prevention for filename**
  - **Validates: Requirements 3.2**

- [ ]* 1.3 Write property test for directory containment
  - **Property 13: Directory containment**
  - **Validates: Requirements 3.5**

- [x] 2. Enhance photo aggregation logic in existing API endpoint





  - Modify `/api/events/<event_id>/photos` endpoint to scan both folders
  - Add function to scan uploads folder for original photos
  - Filter uploads folder to only include image files (.jpg, .jpeg, .png)
  - Combine photos from processed folder (group photos only) and uploads folder
  - Implement deduplication logic based on base filename (strip watermarked_ prefix)
  - Prioritize processed photos over originals when duplicates exist
  - Add source metadata ('processed' or 'uploads') to each photo in response
  - Generate correct URLs based on photo source
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.5, 4.1, 4.2, 4.3_

- [ ]* 2.1 Write property test for multi-source aggregation
  - **Property 2: Multi-source photo aggregation**
  - **Validates: Requirements 1.2, 2.1**

- [ ]* 2.2 Write property test for fallback to originals
  - **Property 3: Fallback to original photos**
  - **Validates: Requirements 1.3**

- [ ]* 2.3 Write property test for processed photo priority
  - **Property 4: Processed photo priority and deduplication**
  - **Validates: Requirements 1.4, 4.4**

- [ ]* 2.4 Write property test for filename deduplication
  - **Property 5: Filename-based deduplication**
  - **Validates: Requirements 2.2**

- [ ]* 2.5 Write property test for image file filtering
  - **Property 8: Image file filtering**
  - **Validates: Requirements 2.5**

- [ ]* 2.6 Write property test for source metadata accuracy
  - **Property 14: Source metadata accuracy**
  - **Validates: Requirements 4.1, 4.2**

- [x] 3. Add helper function for photo deduplication





  - Create function to remove duplicate photos based on base filename
  - Handle watermarked_ prefix removal for comparison
  - Prioritize processed photos over uploads when duplicates found
  - Return deduplicated list with source metadata
  - _Requirements: 1.4, 2.2_

- [x] 4. Update error handling for empty photo scenarios




  - Modify API response to handle case when no photos exist in either folder
  - Return success=true with empty photos array and helpful message
  - Ensure frontend displays appropriate "No photos available" message
  - _Requirements: 1.5_

- [ ] 5. Checkpoint - Ensure all tests pass














  - Ensure all tests pass, ask the user if questions arise.
