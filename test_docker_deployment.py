#!/usr/bin/env python3
"""
Docker Deployment Test Script for PicMe Photo Serving Fix

This script tests the photo serving functionality in a Docker environment:
1. Builds the Docker image
2. Starts the container with volume mounts
3. Uploads test photos
4. Verifies photo processing
5. Tests photo accessibility via both endpoints
6. Checks for 404 errors

Requirements: 3.1, 3.7
"""

import os
import sys
import time
import requests
import subprocess
import json
from pathlib import Path

# Configuration
DOCKER_IMAGE_NAME = "picme-test"
CONTAINER_NAME = "picme-test-container"
HOST_PORT = 8080
CONTAINER_PORT = 8080
BASE_URL = f"http://localhost:{HOST_PORT}"

# Test data
TEST_EVENT_ID = f"test_event_{int(time.time())}"
TEST_PHOTOS_DIR = Path("test_photos")


def print_section(title):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def run_command(cmd, check=True, capture_output=False):
    """Run a shell command and return the result"""
    print(f"Running: {cmd}")
    if isinstance(cmd, str):
        cmd = cmd.split()
    
    try:
        if capture_output:
            result = subprocess.run(cmd, check=check, capture_output=True, text=True)
            return result
        else:
            result = subprocess.run(cmd, check=check)
            return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        if capture_output and e.stderr:
            print(f"Error output: {e.stderr}")
        if not check:
            return None
        raise


def cleanup_docker():
    """Stop and remove existing test containers and images"""
    print_section("Cleaning up existing Docker resources")
    
    # Stop container if running
    run_command(f"docker stop {CONTAINER_NAME}", check=False)
    
    # Remove container
    run_command(f"docker rm {CONTAINER_NAME}", check=False)
    
    print("Cleanup complete")


def build_docker_image():
    """Build the Docker image with latest changes"""
    print_section("Building Docker Image")
    
    print("Building image (this may take a few minutes)...")
    result = run_command(f"docker build -t {DOCKER_IMAGE_NAME} .", check=True)
    
    if result.returncode == 0:
        print("✓ Docker image built successfully")
        return True
    else:
        print("✗ Failed to build Docker image")
        return False


def start_container():
    """Start the Docker container with volume mounts"""
    print_section("Starting Docker Container")
    
    # Create volume mount directories if they don't exist
    uploads_dir = Path("uploads").absolute()
    processed_dir = Path("processed").absolute()
    events_file = Path("events_data.json").absolute()
    
    uploads_dir.mkdir(exist_ok=True)
    processed_dir.mkdir(exist_ok=True)
    
    if not events_file.exists():
        with open(events_file, 'w') as f:
            json.dump([], f)
    
    # Start container with volume mounts
    cmd = [
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "-p", f"{HOST_PORT}:{CONTAINER_PORT}",
        "-v", f"{uploads_dir}:/app/uploads",
        "-v", f"{processed_dir}:/app/processed",
        "-v", f"{events_file}:/app/events_data.json",
        DOCKER_IMAGE_NAME
    ]
    
    result = run_command(cmd, check=True)
    
    if result.returncode == 0:
        print(f"✓ Container started: {CONTAINER_NAME}")
        
        # Wait for container to be ready
        print("Waiting for application to start...")
        max_retries = 30
        for i in range(max_retries):
            try:
                response = requests.get(f"{BASE_URL}/", timeout=2)
                if response.status_code == 200:
                    print(f"✓ Application is ready (took {i+1} seconds)")
                    return True
            except requests.exceptions.RequestException:
                pass
            
            time.sleep(1)
            if i % 5 == 0:
                print(f"  Still waiting... ({i}/{max_retries})")
        
        print("✗ Application did not start in time")
        return False
    else:
        print("✗ Failed to start container")
        return False


def create_test_photos():
    """Create test photos for upload"""
    print_section("Creating Test Photos")
    
    TEST_PHOTOS_DIR.mkdir(exist_ok=True)
    
    # Create simple test images using PIL
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Create 3 test photos
        for i in range(1, 4):
            img = Image.new('RGB', (800, 600), color=(100 + i*30, 150, 200))
            draw = ImageDraw.Draw(img)
            
            # Add text to make photos distinguishable
            text = f"Test Photo {i}"
            draw.text((400, 300), text, fill=(255, 255, 255))
            
            photo_path = TEST_PHOTOS_DIR / f"test_photo_{i}.jpg"
            img.save(photo_path, 'JPEG')
            print(f"✓ Created: {photo_path}")
        
        return True
    except ImportError:
        print("PIL not available, creating placeholder files")
        # Create placeholder files
        for i in range(1, 4):
            photo_path = TEST_PHOTOS_DIR / f"test_photo_{i}.jpg"
            with open(photo_path, 'wb') as f:
                # Write minimal JPEG header
                f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF')
            print(f"✓ Created placeholder: {photo_path}")
        return True


def create_test_event():
    """Create a test event via API"""
    print_section("Creating Test Event")
    
    # First, we need to register and login
    # For testing, we'll create the event directly in events_data.json
    events_file = Path("events_data.json")
    
    try:
        with open(events_file, 'r') as f:
            events = json.load(f)
    except:
        events = []
    
    # Add test event
    test_event = {
        "id": TEST_EVENT_ID,
        "name": "Docker Test Event",
        "location": "Test Location",
        "date": "2024-12-23",
        "category": "Testing",
        "thumbnail": "/static/images/default_event.jpg"
    }
    
    events.append(test_event)
    
    with open(events_file, 'w') as f:
        json.dump(events, f, indent=2)
    
    print(f"✓ Created test event: {TEST_EVENT_ID}")
    return TEST_EVENT_ID


def upload_test_photos(event_id):
    """Upload test photos to the event"""
    print_section("Uploading Test Photos")
    
    # Create event upload directory
    upload_dir = Path("uploads") / event_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy test photos to upload directory
    uploaded_files = []
    for photo in TEST_PHOTOS_DIR.glob("*.jpg"):
        dest = upload_dir / photo.name
        import shutil
        shutil.copy(photo, dest)
        uploaded_files.append(photo.name)
        print(f"✓ Uploaded: {photo.name}")
    
    return uploaded_files


def wait_for_processing(event_id, timeout=60):
    """Wait for photo processing to complete"""
    print_section("Waiting for Photo Processing")
    
    processed_dir = Path("processed") / event_id
    start_time = time.time()
    
    print(f"Monitoring: {processed_dir}")
    
    while time.time() - start_time < timeout:
        if processed_dir.exists():
            # Check if any person folders exist
            person_folders = list(processed_dir.glob("person_*"))
            if person_folders:
                print(f"✓ Processing complete! Found {len(person_folders)} person folder(s)")
                return True
        
        time.sleep(2)
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0:
            print(f"  Still processing... ({elapsed}/{timeout}s)")
    
    print("⚠ Processing timeout - photos may not have faces or processing is slow")
    return False


def test_photo_endpoints(event_id, uploaded_files):
    """Test that photos are accessible via both endpoints"""
    print_section("Testing Photo Endpoints")
    
    errors = []
    success_count = 0
    
    # Test 1: Uploads endpoint
    print("\n1. Testing uploads endpoint (/api/events/<event_id>/uploads/<filename>)")
    for filename in uploaded_files:
        url = f"{BASE_URL}/api/events/{event_id}/uploads/{filename}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"  ✓ {filename}: 200 OK ({len(response.content)} bytes)")
                success_count += 1
            else:
                error_msg = f"  ✗ {filename}: {response.status_code}"
                print(error_msg)
                errors.append(error_msg)
        except Exception as e:
            error_msg = f"  ✗ {filename}: {str(e)}"
            print(error_msg)
            errors.append(error_msg)
    
    # Test 2: Processed photos endpoint (if processing completed)
    print("\n2. Testing processed photos endpoint (/photos/<event_id>/all/<filename>)")
    processed_dir = Path("processed") / event_id
    if processed_dir.exists():
        # Find watermarked photos
        watermarked_photos = []
        for person_folder in processed_dir.glob("person_*"):
            group_dir = person_folder / "group"
            if group_dir.exists():
                watermarked_photos.extend(group_dir.glob("watermarked_*.jpg"))
        
        if watermarked_photos:
            for photo_path in watermarked_photos[:3]:  # Test first 3
                filename = photo_path.name
                url = f"{BASE_URL}/photos/{event_id}/all/{filename}"
                try:
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        print(f"  ✓ {filename}: 200 OK ({len(response.content)} bytes)")
                        success_count += 1
                    else:
                        error_msg = f"  ✗ {filename}: {response.status_code}"
                        print(error_msg)
                        errors.append(error_msg)
                except Exception as e:
                    error_msg = f"  ✗ {filename}: {str(e)}"
                    print(error_msg)
                    errors.append(error_msg)
        else:
            print("  ⚠ No watermarked photos found (processing may not have detected faces)")
    else:
        print("  ⚠ Processed folder not found (processing may not have completed)")
    
    # Test 3: Photo aggregation API
    print("\n3. Testing photo aggregation API (/api/events/<event_id>/photos)")
    url = f"{BASE_URL}/api/events/{event_id}/photos"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                photos = data.get('photos', [])
                print(f"  ✓ Aggregation API: {len(photos)} photos returned")
                success_count += 1
                
                # Verify no 404s in photo URLs
                print("\n4. Verifying photo URLs from aggregation API")
                for i, photo_url in enumerate(photos[:5]):  # Test first 5
                    full_url = f"{BASE_URL}{photo_url}"
                    try:
                        response = requests.get(full_url, timeout=5)
                        if response.status_code == 200:
                            print(f"  ✓ Photo {i+1}: 200 OK")
                            success_count += 1
                        else:
                            error_msg = f"  ✗ Photo {i+1}: {response.status_code} - {photo_url}"
                            print(error_msg)
                            errors.append(error_msg)
                    except Exception as e:
                        error_msg = f"  ✗ Photo {i+1}: {str(e)} - {photo_url}"
                        print(error_msg)
                        errors.append(error_msg)
            else:
                error_msg = f"  ✗ Aggregation API returned success=false"
                print(error_msg)
                errors.append(error_msg)
        else:
            error_msg = f"  ✗ Aggregation API: {response.status_code}"
            print(error_msg)
            errors.append(error_msg)
    except Exception as e:
        error_msg = f"  ✗ Aggregation API: {str(e)}"
        print(error_msg)
        errors.append(error_msg)
    
    return success_count, errors


def check_container_logs():
    """Check container logs for errors"""
    print_section("Checking Container Logs")
    
    result = run_command(f"docker logs {CONTAINER_NAME}", check=False, capture_output=True)
    
    if result and result.stdout:
        logs = result.stdout
        
        # Look for errors
        error_lines = [line for line in logs.split('\n') if 'ERROR' in line or '404' in line]
        
        if error_lines:
            print("⚠ Found errors in logs:")
            for line in error_lines[-10:]:  # Show last 10 errors
                print(f"  {line}")
        else:
            print("✓ No errors found in logs")
        
        # Show last few lines
        print("\nLast 10 log lines:")
        for line in logs.split('\n')[-10:]:
            if line.strip():
                print(f"  {line}")
    else:
        print("✗ Could not retrieve logs")


def print_summary(success_count, errors):
    """Print test summary"""
    print_section("Test Summary")
    
    total_tests = success_count + len(errors)
    
    print(f"Total tests: {total_tests}")
    print(f"Passed: {success_count}")
    print(f"Failed: {len(errors)}")
    
    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  {error}")
    
    if len(errors) == 0:
        print("\n✓ All tests passed!")
        return True
    else:
        print(f"\n✗ {len(errors)} test(s) failed")
        return False


def main():
    """Main test execution"""
    print_section("Docker Deployment Test - Photo Serving Fix")
    
    try:
        # Step 1: Cleanup
        cleanup_docker()
        
        # Step 2: Build image
        if not build_docker_image():
            print("\n✗ Build failed, aborting tests")
            return False
        
        # Step 3: Start container
        if not start_container():
            print("\n✗ Container start failed, aborting tests")
            return False
        
        # Step 4: Create test photos
        if not create_test_photos():
            print("\n✗ Failed to create test photos")
            return False
        
        # Step 5: Create test event
        event_id = create_test_event()
        
        # Step 6: Upload photos
        uploaded_files = upload_test_photos(event_id)
        
        # Step 7: Wait for processing
        wait_for_processing(event_id, timeout=60)
        
        # Step 8: Test endpoints
        success_count, errors = test_photo_endpoints(event_id, uploaded_files)
        
        # Step 9: Check logs
        check_container_logs()
        
        # Step 10: Summary
        success = print_summary(success_count, errors)
        
        return success
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup option
        print("\n" + "=" * 80)
        response = input("Stop and remove test container? (y/n): ")
        if response.lower() == 'y':
            cleanup_docker()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
