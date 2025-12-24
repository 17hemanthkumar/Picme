#!/usr/bin/env python3
"""
Docker Readiness Verification Script

This script verifies that all code changes for the photo serving fix are in place
and the application is ready for Docker deployment testing.

This does NOT require Docker to be running - it only checks the code.
"""

import os
import re
from pathlib import Path


def print_header(title):
    """Print a formatted header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def check_file_exists(filepath, description):
    """Check if a file exists"""
    if os.path.exists(filepath):
        print(f"✓ {description}: {filepath}")
        return True
    else:
        print(f"✗ {description} NOT FOUND: {filepath}")
        return False


def check_code_contains(filepath, pattern, description):
    """Check if a file contains a specific pattern"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if re.search(pattern, content, re.MULTILINE):
                print(f"✓ {description}")
                return True
            else:
                print(f"✗ {description} NOT FOUND")
                return False
    except Exception as e:
        print(f"✗ Error checking {filepath}: {e}")
        return False


def main():
    """Main verification"""
    print_header("Docker Readiness Verification - Photo Serving Fix")
    
    checks_passed = 0
    checks_failed = 0
    
    # Check 1: Dockerfile exists
    print_header("1. Docker Configuration")
    if check_file_exists("Dockerfile", "Dockerfile"):
        checks_passed += 1
        
        # Check Dockerfile contents
        if check_code_contains("Dockerfile", r"COPY uploads /app/uploads", "Uploads folder copied"):
            checks_passed += 1
        else:
            checks_failed += 1
            
        if check_code_contains("Dockerfile", r"COPY processed /app/processed", "Processed folder copied"):
            checks_passed += 1
        else:
            checks_failed += 1
            
        if check_code_contains("Dockerfile", r"COPY events_data.json", "Events data copied"):
            checks_passed += 1
        else:
            checks_failed += 1
    else:
        checks_failed += 1
    
    # Check 2: Backend app.py has uploads endpoint
    print_header("2. Photo Serving Endpoints")
    if check_file_exists("backend/app.py", "Backend application"):
        checks_passed += 1
        
        # Check for uploads endpoint
        if check_code_contains("backend/app.py", 
                              r"@app\.route\('/api/events/<event_id>/uploads/<filename>'\)",
                              "Uploads endpoint defined"):
            checks_passed += 1
        else:
            checks_failed += 1
        
        # Check for serve_upload_photo function
        if check_code_contains("backend/app.py",
                              r"def serve_upload_photo\(event_id, filename\):",
                              "Upload photo serving function"):
            checks_passed += 1
        else:
            checks_failed += 1
        
        # Check for path sanitization
        if check_code_contains("backend/app.py",
                              r"sanitize_path_component\(event_id\)",
                              "Path sanitization for event_id"):
            checks_passed += 1
        else:
            checks_failed += 1
        
        if check_code_contains("backend/app.py",
                              r"sanitize_filename\(filename\)",
                              "Filename sanitization"):
            checks_passed += 1
        else:
            checks_failed += 1
    else:
        checks_failed += 1
    
    # Check 3: Photo aggregation logic
    print_header("3. Photo Aggregation Logic")
    if check_code_contains("backend/app.py",
                          r"def scan_uploads_folder\(event_id\):",
                          "scan_uploads_folder function"):
        checks_passed += 1
    else:
        checks_failed += 1
    
    if check_code_contains("backend/app.py",
                          r"def scan_processed_folder\(event_id\):",
                          "scan_processed_folder function"):
        checks_passed += 1
    else:
        checks_failed += 1
    
    if check_code_contains("backend/app.py",
                          r"def deduplicate_photos\(",
                          "deduplicate_photos function"):
        checks_passed += 1
    else:
        checks_failed += 1
    
    # Check 4: Photo processing
    print_header("4. Photo Processing")
    if check_code_contains("backend/app.py",
                          r"def process_images\(event_id\):",
                          "process_images function"):
        checks_passed += 1
    else:
        checks_failed += 1
    
    if check_code_contains("backend/app.py",
                          r"\[PHOTO_PROCESSING\]",
                          "Photo processing logging"):
        checks_passed += 1
    else:
        checks_failed += 1
    
    # Check 5: Error handling
    print_header("5. Error Handling and Logging")
    if check_code_contains("backend/app.py",
                          r"logger\.error\(.*PHOTO_SERVING",
                          "Photo serving error logging"):
        checks_passed += 1
    else:
        checks_failed += 1
    
    if check_code_contains("backend/app.py",
                          r"logger\.warning\(.*SECURITY",
                          "Security violation logging"):
        checks_passed += 1
    else:
        checks_failed += 1
    
    # Check 6: Property-based tests
    print_header("6. Property-Based Tests")
    test_files = [
        ("backend/test_photo_serving_properties.py", "Photo serving properties"),
        ("backend/test_photo_aggregation_properties.py", "Photo aggregation properties"),
        ("backend/test_photo_processing_properties.py", "Photo processing properties")
    ]
    
    for test_file, description in test_files:
        if check_file_exists(test_file, description):
            checks_passed += 1
        else:
            checks_failed += 1
    
    # Check 7: Directory structure
    print_header("7. Directory Structure")
    directories = [
        ("uploads", "Uploads folder"),
        ("processed", "Processed folder")
    ]
    
    for directory, description in directories:
        if os.path.exists(directory) and os.path.isdir(directory):
            print(f"✓ {description} exists: {directory}")
            checks_passed += 1
        else:
            print(f"⚠ {description} not found (will be created): {directory}")
            # Not counting as failure since these can be created
    
    # Check 8: Events data
    print_header("8. Events Data")
    if check_file_exists("events_data.json", "Events data file"):
        checks_passed += 1
    else:
        print("⚠ events_data.json not found (will be created)")
    
    # Summary
    print_header("Verification Summary")
    total_checks = checks_passed + checks_failed
    print(f"\nTotal checks: {total_checks}")
    print(f"Passed: {checks_passed}")
    print(f"Failed: {checks_failed}")
    
    if checks_failed == 0:
        print("\n✓ All critical checks passed!")
        print("✓ Application is ready for Docker deployment testing")
        print("\nNext steps:")
        print("1. Ensure Docker Desktop is running")
        print("2. Follow the DOCKER_TESTING_GUIDE.md for manual testing")
        print("3. Or run: python test_docker_deployment.py for automated testing")
        return True
    else:
        print(f"\n✗ {checks_failed} check(s) failed")
        print("✗ Please fix the issues above before Docker testing")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
