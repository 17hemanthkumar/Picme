# Docker Photo Serving Test Guide

This guide walks through testing the photo serving functionality in Docker environment.

## Prerequisites

1. Docker Desktop must be running
2. All code changes from tasks 1-4 must be complete

## Test Steps

### Step 1: Build Docker Image

```bash
docker build -t picme .
```

**Expected Result:** Build completes successfully without errors.

### Step 2: Start Container with Volume Mounts

```bash
docker run -d --name picme-test -p 8080:8080 \
  -v "%cd%/uploads:/app/uploads" \
  -v "%cd%/processed:/app/processed" \
  -v "%cd%/events_data.json:/app/events_data.json" \
  picme
```

**Expected Result:** Container starts and application becomes accessible.

### Step 3: Verify Application is Running

Open browser to: http://localhost:8080

**Expected Result:** Homepage loads without errors.

### Step 4: Check Container Logs

```bash
docker logs picme-test
```

**Expected Result:** 
- No critical errors
- See "ML MODEL Loaded X identities" message
- See "Application will run on port: 8080"

### Step 5: Create Test Event

1. Navigate to http://localhost:8080/login
2. Register a new organizer account
3. Login and go to Event Organizer page
4. Create a new event with:
   - Name: "Docker Test Event 1"
   - Location: "Test Location"
   - Date: Any future date
   - Upload a thumbnail image

**Expected Result:** Event created successfully, event_id displayed.

### Step 6: Upload Test Photos

1. On the Event Organizer page, select the event you just created
2. Upload 2-3 test photos (any JPG/PNG images)
3. Click "Upload Photos"

**Expected Result:** 
- Photos upload successfully
- Success message displayed
- Photos appear in uploads folder

### Step 7: Verify Photo Processing

Wait 10-30 seconds, then check:

```bash
docker logs picme-test --tail 50
```

**Expected Result:**
- See "[PHOTO_PROCESSING] Starting processing for event: event_XXXXXXXX"
- See "[PHOTO_PROCESSING] Processing image" messages
- See "[PHOTO_PROCESSING] Face detection complete" messages
- See "[PHOTO_PROCESSING] Processing complete" message

### Step 8: Check Uploads Folder

```bash
dir uploads\event_*
```

**Expected Result:** See your uploaded photos in the event folder.

### Step 9: Check Processed Folder (if faces detected)

```bash
dir processed\event_*
```

**Expected Result:** 
- If photos contained faces: See person_id folders with individual/group subfolders
- If no faces: Folder may be empty (this is OK)

### Step 10: Test Uploads Endpoint

Open browser and navigate to:
```
http://localhost:8080/api/events/<event_id>/uploads/<filename>
```

Replace `<event_id>` with your event ID and `<filename>` with one of your uploaded photo names.

**Expected Result:** Photo displays in browser, no 404 error.

### Step 11: Test Photo Aggregation API

Open browser DevTools (F12) and navigate to:
```
http://localhost:8080/api/events/<event_id>/photos
```

**Expected Result:**
- JSON response with list of photo URLs
- All URLs should be valid (no 404s when clicked)

### Step 12: Test Event Gallery View

1. Navigate to http://localhost:8080/event_discovery
2. Find your test event
3. Click to view event details

**Expected Result:**
- Event photos display correctly
- No 404 errors in browser console (check DevTools Console tab)
- Photos load from both uploads and processed folders

### Step 13: Create Second Test Event

Repeat steps 5-12 with a second event named "Docker Test Event 2".

**Expected Result:** All tests pass for second event as well.

### Step 14: Verify No 404 Errors

1. Open browser DevTools (F12)
2. Go to Console tab
3. Navigate through event discovery and event detail pages
4. Check Network tab for any failed requests

**Expected Result:** 
- No 404 errors for photo URLs
- All photo requests return 200 status
- Photos display correctly

## Cleanup

Stop and remove the test container:

```bash
docker stop picme-test
docker rm picme-test
```

## Success Criteria

All of the following must be true:

✅ Docker image builds successfully  
✅ Container starts and application is accessible  
✅ Events can be created via web interface  
✅ Photos can be uploaded to events  
✅ Photo processing occurs (logs show processing activity)  
✅ Uploads endpoint serves photos correctly (no 404)  
✅ Processed endpoint serves photos correctly (if faces detected)  
✅ Photo aggregation API returns valid URLs  
✅ Event gallery displays photos without 404 errors  
✅ Multiple events work correctly  

## Troubleshooting

### Container won't start
- Check Docker Desktop is running
- Check port 8080 is not already in use
- Review container logs: `docker logs picme-test`

### Photos not processing
- Check container logs for errors
- Verify uploads folder has photos
- Processing may take 10-30 seconds
- Test photos without faces won't create processed folders (this is OK)

### 404 errors for photos
- Verify uploads endpoint exists in app.py
- Check photo aggregation logic uses correct URL format
- Verify volume mounts are working: `docker exec picme-test ls /app/uploads`

### Database connection errors
- Check DATABASE_URL environment variable
- For testing, you can use SQLite instead of PostgreSQL

## Requirements Validated

This test validates:
- **Requirement 3.1:** Photos are uploaded and processing is triggered
- **Requirement 3.7:** Processing handles errors gracefully and continues

## Notes

- Test photos without faces are OK - they won't create processed folders
- Processing time depends on photo size and number of faces
- Volume mounts ensure data persists between container restarts
- Check container logs frequently for debugging
