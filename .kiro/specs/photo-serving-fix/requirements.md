# Requirements Document

## Introduction

The PicMe photo sharing application currently has critical issues with photo loading and display. Photos are not being served correctly, resulting in 404 errors and broken images. Additionally, uploaded photos are not being processed properly in the Docker environment, leading to duplicates and missing processed images. This feature will fix the photo serving infrastructure and ensure proper image processing.

## Glossary

- **Upload Folder**: Directory where original photos are initially stored after upload (`uploads/`)
- **Processed Folder**: Directory where face-recognized and categorized photos are stored (`processed/`)
- **Watermarked Photo**: Group photo with watermark prefix (`watermarked_*`)
- **Original Photo**: Unprocessed photo in the uploads folder
- **Event Gallery**: Public-facing photo display showing all photos for an event
- **Photo Processing**: Face recognition and categorization workflow that moves photos from uploads to processed folders

## Requirements

### Requirement 1

**User Story:** As a user viewing an event gallery, I want all photos to load correctly without 404 errors, so that I can see all available event photos.

#### Acceptance Criteria

1. WHEN the system serves a photo from the uploads folder THEN the system SHALL provide a valid HTTP endpoint that returns the photo file
2. WHEN a photo URL is requested THEN the system SHALL sanitize the path components to prevent directory traversal attacks
3. WHEN a photo file exists in the uploads folder THEN the system SHALL serve it with the correct MIME type
4. WHEN a photo file does not exist THEN the system SHALL return a 404 status code with an appropriate error message
5. WHEN multiple photos are requested THEN the system SHALL serve each photo independently without caching issues

### Requirement 2

**User Story:** As a user viewing an event gallery, I want to see processed photos when available and original photos as fallback, so that I always have access to event photos regardless of processing status.

#### Acceptance Criteria

1. WHEN the system aggregates photos for an event THEN the system SHALL scan both processed and uploads folders
2. WHEN a photo exists in both processed and uploads folders THEN the system SHALL prioritize the processed version
3. WHEN the system deduplicates photos THEN the system SHALL compare base filenames after removing the watermarked prefix
4. WHEN no processed photos exist THEN the system SHALL serve original photos from the uploads folder
5. WHEN the system returns photo URLs THEN the system SHALL use the correct endpoint path for each photo source

### Requirement 3

**User Story:** As an event organizer, I want uploaded photos to be processed automatically in Docker, so that face recognition and categorization happen reliably.

#### Acceptance Criteria

1. WHEN photos are uploaded to an event THEN the system SHALL trigger background processing
2. WHEN the processing thread starts THEN the system SHALL detect all faces in each uploaded photo
3. WHEN faces are detected THEN the system SHALL learn or update face encodings in the model
4. WHEN a photo contains one face THEN the system SHALL copy it to the individual folder for that person
5. WHEN a photo contains multiple faces THEN the system SHALL copy it with watermark prefix to the group folder for each detected person
6. WHEN processing completes THEN the system SHALL have created the appropriate folder structure in the processed directory
7. WHEN processing encounters an error THEN the system SHALL log the error and continue processing remaining photos

### Requirement 4

**User Story:** As a developer, I want proper error handling and logging for photo operations, so that I can diagnose and fix issues quickly.

#### Acceptance Criteria

1. WHEN a photo serving operation fails THEN the system SHALL log the error with relevant context
2. WHEN a path traversal attempt is detected THEN the system SHALL reject the request and log the security violation
3. WHEN a file operation fails THEN the system SHALL return an appropriate HTTP status code
4. WHEN processing photos THEN the system SHALL log progress and any errors encountered
5. WHEN the system cannot find a requested photo THEN the system SHALL provide a clear error message indicating which photo and folder were checked
