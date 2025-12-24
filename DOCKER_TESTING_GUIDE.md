# Docker Testing Guide - Photo Serving Fix

This guide provides step-by-step instructions for testing the photo serving fix in a Docker environment.

**Requirements Validated:** 3.1, 3.7

## Prerequisites

- Docker Desktop installed and running
- Python 3.10+ (for creating test photos)
- Terminal/Command Prompt access

## Test Overview

This test validates:
1. ✅ Docker image builds successfully with latest changes
2. ✅ Container starts with volume mounts for uploads and processed folders
3. ✅ Photos can be uploaded and processing occurs
4. ✅ Photos are accessible via uploads endpoint (`/api/events/<event_id>/uploads/<filename>`)
5. ✅ Photos are accessible via processed endpoint (`/photos/<event_id>/all/<filename>`)
6. ✅ No 404 errors occur when loading photos
7. ✅ Multiple events and photo uploads work correctly

---

## Step 1: Build Docker Image

Build the Docker image with all the latest changes:

```bash
docker build -t picme .
```

**Expected Output:**
- Build completes successfully
- No errors during dependency installation
- Image is created: `picme:latest`

**Verification:**
```bash
docker images | grep picme
```

---

## Step 2: Start Container with Volume Mounts

Start the container with volume mounts to persist data:

```bash
docker run -d \
  --name picme-test \
  -p 8080:8080 \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/processed:/app/processed \
  -v $(pwd)/events_data.json:/app/events_data.json \
  picme
```

**For Windows PowerShell:**
```powershell
docker run -d `
  --name picme-test `
  -p 8080:8080 `
  -v ${PWD}/uploads:/app/uploads `
  -v ${PWD}/processed:/app/processed `
  -v ${PWD}/events_data.json:/app/events_data.json `
  picme
```

**Expected Output:**
- Container ID is displayed
- Container is running

**Verification:**
```bash
docker ps | grep picme-test
```

**Check logs:**
```bash
docker logs picme-test
```

Look for:
- `ML MODEL Loaded X identities`
- `Application will run on port: 8080`
- No error messages

---

## Step 3: Wait for Application to Start

The application needs time to load the ML model. Wait for it to be ready:

```bash
# Check logs until you see the model loaded message
docker logs -f picme-test
```

**Expected Output:**
```
[INFO] ML MODEL Loaded X identities
[INFO] Application will run on port: 8080
```

**Test readiness:**
```bash
curl http://localhost:8080/
```

Should return HTML content (status 200).

---

## Step 4: Create Test Event

Create a test event in `events_data.json`:

```json
[
  {
    "id": "test_event_001",
    "name": "Docker Test Event",
    "location": "Test Location",
    "date": "2024-12-23",
    "category": "Testing",
    "thumbnail": "/static/images/default_event.jpg"
  }
]
```

**Verification:**
```bash
curl http://localhost:8080/api/events
```

Should return the event data.

---

## Step 5: Upload Test Photos

Create test photos and upload them:

### Option A: Use Existing Photos

Copy some test photos to the uploads folder:

```bash
mkdir -p uploads/test_event_001
cp /path/to/test/photos/*.jpg uploads/test_event_001/
```

### Option B: Create Test Photos with Python

```python
from PIL import Image, ImageDraw

for i in range(1, 4):
    img = Image.new('RGB', (800, 600), color=(100 + i*30, 150, 200))
    draw = ImageDraw.Draw(img)
    draw.text((400, 300), f"Test Photo {i}", fill=(255, 255, 255))
    img.save(f"uploads/test_event_001/test_photo_{i}.jpg", 'JPEG')
```

**Verification:**
```bash
ls -la uploads/test_event_001/
```

Should show your uploaded photos.

---

## Step 6: Verify Photo Processing

Watch the container logs to see processing occur:

```bash
docker logs -f picme-test
```

**Expected Log Output:**
```
[PHOTO_PROCESSING] Starting processing for event: test_event_001
[PHOTO_PROCESSING] Processing image - event_id: test_event_001, filename: test_photo_1.jpg
[PHOTO_PROCESSING] Face detection complete - faces_detected: 1
[PHOTO_PROCESSING] Copied individual photo - person_id: person_0
[PHOTO_PROCESSING] Processing complete - photos_processed: 3
```

**Check processed folder:**
```bash
ls -la processed/test_event_001/
```

Should show person folders (e.g., `person_0`, `person_1`).

**Check folder structure:**
```bash
tree processed/test_event_001/
```

Expected structure:
```
processed/test_event_001/
├── person_0/
│   ├── individual/
│   │   └── test_photo_1.jpg
│   └── group/
│       └── watermarked_test_photo_2.jpg
```

---

## Step 7: Test Photo Endpoints

### Test 1: Uploads Endpoint

Test that original photos are accessible:

```bash
curl -I http://localhost:8080/api/events/test_event_001/uploads/test_photo_1.jpg
```

**Expected Output:**
```
HTTP/1.1 200 OK
Content-Type: image/jpeg
```

### Test 2: Processed Photos Endpoint

Test that processed photos are accessible:

```bash
curl -I http://localhost:8080/photos/test_event_001/all/watermarked_test_photo_2.jpg
```

**Expected Output:**
```
HTTP/1.1 200 OK
Content-Type: image/jpeg
```

### Test 3: Photo Aggregation API

Test that the aggregation API returns all photos:

```bash
curl http://localhost:8080/api/events/test_event_001/photos
```

**Expected Output:**
```json
{
  "success": true,
  "photos": [
    "/photos/test_event_001/all/watermarked_test_photo_2.jpg",
    "/api/events/test_event_001/uploads/test_photo_1.jpg",
    "/api/events/test_event_001/uploads/test_photo_3.jpg"
  ],
  "has_next": false
}
```

### Test 4: Verify No 404 Errors

Test each photo URL from the aggregation API:

```bash
# For each URL in the photos array
curl -I http://localhost:8080/photos/test_event_001/all/watermarked_test_photo_2.jpg
curl -I http://localhost:8080/api/events/test_event_001/uploads/test_photo_1.jpg
curl -I http://localhost:8080/api/events/test_event_001/uploads/test_photo_3.jpg
```

**All should return:** `HTTP/1.1 200 OK`

---

## Step 8: Test in Browser

Open your browser and test the full user experience:

### 8.1: Access Application

Navigate to: `http://localhost:8080`

**Expected:** Homepage loads without errors

### 8.2: Check Browser Console

Open DevTools (F12) → Console tab

**Expected:** No 404 errors for photo requests

### 8.3: View Event Gallery

1. Navigate to event detail page for `test_event_001`
2. Check that all photos load correctly
3. Verify no broken image icons

**Expected:** All photos display correctly

### 8.4: Check Network Tab

Open DevTools (F12) → Network tab

Filter by: `Images`

**Expected:**
- All photo requests return 200 OK
- No 404 errors
- Photos load from both `/api/events/.../uploads/` and `/photos/.../all/` endpoints

---

## Step 9: Test Multiple Events

Create a second event and repeat the upload process:

```bash
mkdir -p uploads/test_event_002
cp /path/to/more/photos/*.jpg uploads/test_event_002/
```

Add to `events_data.json`:
```json
{
  "id": "test_event_002",
  "name": "Second Test Event",
  "location": "Another Location",
  "date": "2024-12-24",
  "category": "Testing"
}
```

**Verify:**
- Processing occurs for the new event
- Photos are accessible via both endpoints
- No interference with first event's photos

---

## Step 10: Test Path Traversal Protection

Test that security measures prevent path traversal:

```bash
# Should return 404 (not allow access to parent directories)
curl -I http://localhost:8080/api/events/../../../etc/uploads/test.jpg
curl -I http://localhost:8080/api/events/test_event_001/uploads/../../etc/passwd
```

**Expected:** Both return 404 or 400 (not 200)

---

## Step 11: Check Container Logs

Review logs for any errors:

```bash
docker logs picme-test | grep ERROR
docker logs picme-test | grep 404
```

**Expected:** No unexpected errors or 404s

---

## Test Results Checklist

Mark each item as you verify it:

- [ ] Docker image builds successfully
- [ ] Container starts with volume mounts
- [ ] Application loads (ML model initializes)
- [ ] Test event is accessible via API
- [ ] Photos upload to uploads folder
- [ ] Photo processing occurs automatically
- [ ] Processed folder structure is created correctly
- [ ] Uploads endpoint serves photos (200 OK)
- [ ] Processed endpoint serves photos (200 OK)
- [ ] Photo aggregation API returns all photos
- [ ] All photo URLs from aggregation API work (no 404s)
- [ ] Browser console shows no 404 errors
- [ ] Photos display correctly in event gallery
- [ ] Multiple events work independently
- [ ] Path traversal attempts are blocked
- [ ] Container logs show no unexpected errors

---

## Cleanup

When testing is complete:

```bash
# Stop container
docker stop picme-test

# Remove container
docker rm picme-test

# Optional: Remove test data
rm -rf uploads/test_event_*
rm -rf processed/test_event_*
```

---

## Troubleshooting

### Issue: Container won't start

**Check:**
```bash
docker logs picme-test
```

**Common causes:**
- Port 8080 already in use
- Volume mount paths incorrect
- Missing dependencies in Dockerfile

### Issue: Photos not processing

**Check:**
- Photos contain faces (face detection required)
- Photos are valid JPEG/PNG files
- Container has write permissions to processed folder

**Debug:**
```bash
docker exec -it picme-test ls -la /app/uploads/test_event_001/
docker exec -it picme-test ls -la /app/processed/test_event_001/
```

### Issue: 404 errors for photos

**Check:**
- Photo files exist in uploads folder
- Event ID matches in URL and folder structure
- Filename is correct (case-sensitive)

**Debug:**
```bash
curl -v http://localhost:8080/api/events/test_event_001/uploads/test_photo_1.jpg
```

### Issue: ML model timeout

**Solution:**
- Wait longer (first load can take 2-5 minutes)
- Check logs for "ML MODEL Loaded" message
- Reduce workers in gunicorn_config.py if needed

---

## Success Criteria

The test is successful if:

1. ✅ All photos are accessible via uploads endpoint
2. ✅ All processed photos are accessible via processed endpoint
3. ✅ Photo aggregation API returns complete list
4. ✅ No 404 errors in browser console
5. ✅ Photos display correctly in event gallery
6. ✅ Multiple events work independently
7. ✅ Processing occurs automatically for uploaded photos
8. ✅ Security measures prevent path traversal

---

## Notes

- This test validates Requirements 3.1 (photo processing) and 3.7 (error handling)
- Volume mounts allow you to inspect files on the host system
- Processing may take time depending on photo size and face detection
- Some test photos may not have faces, which is expected behavior
- The test can be repeated with real event photos for more realistic validation

---

## Automated Testing

For automated testing, use the provided script:

```bash
python test_docker_deployment.py
```

This script automates all the steps above and provides a comprehensive test report.

**Note:** Requires Docker to be running and Python with PIL/Pillow installed.
