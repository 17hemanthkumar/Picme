# Requirements Document

## Introduction

This specification addresses the issue where event photos are not displaying properly on the event detail page. Currently, photos uploaded to events are stored in the uploads folder but the event detail page only displays processed photos from the processed folder. When photos haven't been processed yet or processing fails, users see broken image placeholders instead of the actual photos.

## Glossary

- **Event System**: The photo management application that handles event creation, photo uploads, and photo display
- **Uploads Folder**: Directory where original photos are initially stored after upload (`uploads/<event_id>/`)
- **Processed Folder**: Directory where photos are organized by person after face recognition processing (`processed/<event_id>/<person_id>/`)
- **Event Detail Page**: The web page that displays all photos for a specific event
- **Watermarked Photo**: A group photo that has been marked with a watermark prefix
- **Original Photo**: An unprocessed photo in the uploads folder

## Requirements

### Requirement 1

**User Story:** As an event organizer, I want to see all uploaded photos on the event detail page immediately after upload, so that I can verify photos were uploaded successfully before processing completes.

#### Acceptance Criteria

1. WHEN photos are uploaded to an event THEN the Event System SHALL display those photos on the event detail page
2. WHEN the event detail page loads THEN the Event System SHALL check both uploads and processed folders for photos
3. WHEN displaying photos THEN the Event System SHALL show original photos from uploads if processed versions are not available
4. WHEN both original and processed versions exist THEN the Event System SHALL prioritize processed photos over originals
5. WHEN no photos exist in either folder THEN the Event System SHALL display a clear message indicating no photos are available

### Requirement 2

**User Story:** As a user viewing an event, I want to see all available photos regardless of processing status, so that I can view event photos even if face recognition hasn't completed.

#### Acceptance Criteria

1. WHEN the API endpoint receives a request for event photos THEN the Event System SHALL return photos from both processed and uploads folders
2. WHEN combining photos from multiple sources THEN the Event System SHALL remove duplicate photos based on filename
3. WHEN returning photo URLs THEN the Event System SHALL provide correct paths that the browser can load
4. WHEN photos are in the uploads folder THEN the Event System SHALL serve them via a dedicated uploads endpoint
5. WHEN the uploads folder contains non-photo files THEN the Event System SHALL filter to only image files with extensions .jpg, .jpeg, .png

### Requirement 3

**User Story:** As a system administrator, I want the photo serving endpoints to be secure, so that unauthorized users cannot access event photos.

#### Acceptance Criteria

1. WHEN serving photos from uploads folder THEN the Event System SHALL validate the event_id to prevent path traversal attacks
2. WHEN serving photos from uploads folder THEN the Event System SHALL sanitize filenames to prevent directory traversal
3. WHEN a photo request is made THEN the Event System SHALL verify the file exists before attempting to serve it
4. WHEN an invalid path is detected THEN the Event System SHALL return a 404 error
5. WHEN serving files THEN the Event System SHALL only serve files from within the configured uploads directory

### Requirement 4

**User Story:** As a developer, I want clear separation between original and processed photos, so that the system can handle both types appropriately.

#### Acceptance Criteria

1. WHEN the photo API is called THEN the Event System SHALL identify which photos are from uploads versus processed folders
2. WHEN returning photo metadata THEN the Event System SHALL include the source folder for each photo
3. WHEN displaying photos on the frontend THEN the Event System SHALL use appropriate endpoints based on photo source
4. WHEN processed photos become available THEN the Event System SHALL automatically prefer them over originals
5. WHEN the system serves a photo THEN the Event System SHALL use the correct MIME type based on file extension
