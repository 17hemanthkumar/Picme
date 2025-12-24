# Duplicate Photos Fix

## Problem
The event gallery was showing duplicate photos. When a photo contained multiple people (e.g., 3 people), it would appear 3 times in the gallery because:

1. Photo processing detects 3 faces
2. Photo gets copied to each person's group folder with `watermarked_` prefix
3. `scan_processed_folder()` scans all person folders and adds the same photo multiple times

**Example:**
- Photo: `group_photo.jpg` with 3 people detected
- Gets copied to:
  - `processed/event_id/person_001/group/watermarked_group_photo.jpg`
  - `processed/event_id/person_002/group/watermarked_group_photo.jpg`
  - `processed/event_id/person_003/group/watermarked_group_photo.jpg`
- Gallery showed it 3 times!

## Solution
Modified `scan_processed_folder()` function in `backend/app.py` to deduplicate photos by filename.

### Changes Made:
1. Added `seen_filenames` set to track which photos have already been added
2. Before adding a photo, check if filename is already in the set
3. Only add photo if it's the first time we've seen that filename
4. Log when duplicates are skipped

### Code Changes:
```python
def scan_processed_folder(event_id):
    photos = []
    seen_filenames = set()  # NEW: Track filenames to avoid duplicates
    
    # ... scan logic ...
    
    for filename in os.listdir(group_dir):
        if filename.startswith('watermarked_'):
            # NEW: Only add if we haven't seen this filename before
            if filename not in seen_filenames:
                seen_filenames.add(filename)
                photos.append({...})
            else:
                logger.debug(f"Skipping duplicate: {filename}")
```

## Result
✅ Each unique photo now appears only ONCE in the gallery
✅ No more duplicates regardless of how many people are in the photo
✅ All tests pass (14 tests total)

## How It Works Now

**Before Fix:**
- Photo with 3 people → Appears 3 times in gallery
- Photo with 5 people → Appears 5 times in gallery

**After Fix:**
- Photo with 3 people → Appears 1 time in gallery
- Photo with 5 people → Appears 1 time in gallery

## To Apply Changes

Rebuild and restart your Docker container:

```bash
# Stop current container
docker stop <container-id>

# Rebuild image
docker build -t picme-app .

# Start with new fix
docker run -d -p 8080:8080 -v "%cd%/uploads:/app/uploads" -v "%cd%/processed:/app/processed" --env-file backend/.env picme-app
```

## Verification

After restarting:
1. Visit an event detail page
2. Count the photos - each unique photo should appear only once
3. Check Docker logs - should see "Skipping duplicate" messages for photos that appear in multiple person folders

## Technical Details

The deduplication happens at the **aggregation level**, not the storage level:
- Photos are still stored in each person's folder (needed for biometric authentication)
- But when displaying in the public gallery, we only show each unique photo once
- This maintains the privacy model while eliminating visual duplicates
