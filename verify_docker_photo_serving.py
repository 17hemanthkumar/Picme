"""
Docker Photo Serving Verification Script

This script verifies that the Docker environment is ready for photo serving tests.
It checks:
1. Docker is installed and running
2. Dockerfile exists and is properly configured
3. Required folders exist
4. Photo serving endpoints are implemented
5. Photo processing logic is in place

Run this before manual Docker testing.
"""

import subprocess
import os
import sys

class DockerPhotoServingVerifier:
    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        
    def check_docker_installed(self):
        """Check if Docker is installed"""
        print("\n🔍 Checking Docker installation...")
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"  ✅ Docker installed: {result.stdout.strip()}")
                self.checks_passed += 1
                return True
            else:
                print("  ❌ Docker not found")
                self.checks_failed += 1
                return False
        except Exception as e:
            print(f"  ❌ Docker not installed or not in PATH: {e}")
            self.checks_failed += 1
            return False
            
    def check_docker_running(self):
        """Check if Docker daemon is running"""
        print("\n🔍 Checking Docker daemon...")
        try:
            result = subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print("  ✅ Docker daemon is running")
                self.checks_passed += 1
                return True
            else:
                print("  ❌ Docker daemon not running")
                print("  💡 Start Docker Desktop and try again")
                self.checks_failed += 1
                return False
        except Exception as e:
            print(f"  ❌ Cannot connect to Docker daemon: {e}")
            print("  💡 Start Docker Desktop and try again")
            self.checks_failed += 1
            return False
            
    def check_dockerfile_exists(self):
        """Check if Dockerfile exists"""
        print("\n🔍 Checking Dockerfile...")
        if os.path.exists("Dockerfile"):
            print("  ✅ Dockerfile found")
            self.checks_passed += 1
            return True
        else:
            print("  ❌ Dockerfile not found")
            self.checks_failed += 1
            return False
            
    def check_dockerfile_configuration(self):
        """Check Dockerfile has required configurations"""
        print("\n🔍 Checking Dockerfile configuration...")
        
        if not os.path.exists("Dockerfile"):
            print("  ⚠️  Skipping - Dockerfile not found")
            return False
            
        with open("Dockerfile", "r") as f:
            content = f.read()
            
        checks = {
            "COPY backend": "Backend files copied",
            "COPY frontend": "Frontend files copied",
            "COPY events_data.json": "Events data copied",
            "uploads /app/uploads": "Uploads folder copied",
            "processed /app/processed": "Processed folder copied",
            "EXPOSE 8080": "Port 8080 exposed",
            "gunicorn": "Gunicorn configured"
        }
        
        all_passed = True
        for check, description in checks.items():
            if check in content:
                print(f"  ✅ {description}")
            else:
                print(f"  ❌ Missing: {description}")
                all_passed = False
                
        if all_passed:
            self.checks_passed += 1
        else:
            self.checks_failed += 1
            
        return all_passed
        
    def check_required_folders(self):
        """Check required folders exist"""
        print("\n🔍 Checking required folders...")
        
        folders = ["uploads", "processed", "backend", "frontend"]
        all_exist = True
        
        for folder in folders:
            if os.path.exists(folder):
                print(f"  ✅ {folder}/ exists")
            else:
                print(f"  ❌ {folder}/ not found")
                all_exist = False
                
        if all_exist:
            self.checks_passed += 1
        else:
            self.checks_failed += 1
            
        return all_exist
        
    def check_uploads_endpoint(self):
        """Check if uploads endpoint is implemented"""
        print("\n🔍 Checking uploads endpoint implementation...")
        
        app_path = "backend/app.py"
        if not os.path.exists(app_path):
            print("  ❌ backend/app.py not found")
            self.checks_failed += 1
            return False
            
        with open(app_path, "r") as f:
            content = f.read()
            
        if "/api/events/<event_id>/uploads/<filename>" in content:
            print("  ✅ Uploads endpoint implemented")
            self.checks_passed += 1
            return True
        else:
            print("  ❌ Uploads endpoint not found")
            print("  💡 Implement /api/events/<event_id>/uploads/<filename> route")
            self.checks_failed += 1
            return False
            
    def check_photo_aggregation(self):
        """Check if photo aggregation functions exist"""
        print("\n🔍 Checking photo aggregation logic...")
        
        app_path = "backend/app.py"
        if not os.path.exists(app_path):
            print("  ⚠️  Skipping - backend/app.py not found")
            return False
            
        with open(app_path, "r") as f:
            content = f.read()
            
        functions = {
            "scan_uploads_folder": "Scan uploads folder function",
            "scan_processed_folder": "Scan processed folder function",
            "deduplicate_photos": "Deduplication function"
        }
        
        all_found = True
        for func, description in functions.items():
            if f"def {func}" in content:
                print(f"  ✅ {description} found")
            else:
                print(f"  ❌ {description} not found")
                all_found = False
                
        if all_found:
            self.checks_passed += 1
        else:
            self.checks_failed += 1
            
        return all_found
        
    def check_photo_processing(self):
        """Check if photo processing function exists"""
        print("\n🔍 Checking photo processing logic...")
        
        app_path = "backend/app.py"
        if not os.path.exists(app_path):
            print("  ⚠️  Skipping - backend/app.py not found")
            return False
            
        with open(app_path, "r") as f:
            content = f.read()
            
        if "def process_images" in content:
            print("  ✅ Photo processing function found")
            
            # Check for error handling
            if "try:" in content and "except" in content:
                print("  ✅ Error handling present")
            else:
                print("  ⚠️  Error handling may be missing")
                
            # Check for logging
            if "logger.info" in content or "logger.error" in content:
                print("  ✅ Logging implemented")
            else:
                print("  ⚠️  Logging may be missing")
                
            self.checks_passed += 1
            return True
        else:
            print("  ❌ Photo processing function not found")
            self.checks_failed += 1
            return False
            
    def check_property_tests(self):
        """Check if property-based tests exist"""
        print("\n🔍 Checking property-based tests...")
        
        test_files = [
            "backend/test_photo_serving_properties.py",
            "backend/test_photo_aggregation_properties.py",
            "backend/test_photo_processing_properties.py"
        ]
        
        found = 0
        for test_file in test_files:
            if os.path.exists(test_file):
                print(f"  ✅ {os.path.basename(test_file)} exists")
                found += 1
            else:
                print(f"  ⚠️  {os.path.basename(test_file)} not found")
                
        if found > 0:
            print(f"  ✅ Found {found} property test file(s)")
            self.checks_passed += 1
            return True
        else:
            print("  ⚠️  No property test files found")
            self.checks_failed += 1
            return False
            
    def print_summary(self):
        """Print summary of checks"""
        print("\n" + "=" * 60)
        print("Verification Summary")
        print("=" * 60)
        print(f"✅ Checks passed: {self.checks_passed}")
        print(f"❌ Checks failed: {self.checks_failed}")
        
        if self.checks_failed == 0:
            print("\n🎉 All checks passed! Ready for Docker testing.")
            print("\n📋 Next steps:")
            print("   1. Review DOCKER_PHOTO_SERVING_TEST_GUIDE.md")
            print("   2. Start Docker Desktop")
            print("   3. Run: docker build -t picme .")
            print("   4. Follow the manual testing guide")
            return True
        else:
            print("\n⚠️  Some checks failed. Fix issues before Docker testing.")
            return False
            
    def run_all_checks(self):
        """Run all verification checks"""
        print("=" * 60)
        print("Docker Photo Serving Verification")
        print("=" * 60)
        
        self.check_docker_installed()
        self.check_docker_running()
        self.check_dockerfile_exists()
        self.check_dockerfile_configuration()
        self.check_required_folders()
        self.check_uploads_endpoint()
        self.check_photo_aggregation()
        self.check_photo_processing()
        self.check_property_tests()
        
        return self.print_summary()


if __name__ == "__main__":
    verifier = DockerPhotoServingVerifier()
    success = verifier.run_all_checks()
    sys.exit(0 if success else 1)
