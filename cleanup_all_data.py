"""
Script to clean up all events and photos from PicMe application.
This will delete:
- All events from events_data.json
- All photos from uploads folder
- All photos from processed folder
- Face recognition data (known_faces.dat)

USE WITH CAUTION - THIS CANNOT BE UNDONE!
"""

import os
import shutil
import json

def cleanup_all_data():
    """Clean up all events and photos."""
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Paths
    events_data_path = os.path.join(base_dir, 'events_data.json')
    uploads_folder = os.path.join(base_dir, 'uploads')
    processed_folder = os.path.join(base_dir, 'processed')
    known_faces_path = os.path.join(base_dir, 'backend', 'known_faces.dat')
    
    print("=" * 60)
    print("PicMe Data Cleanup Script")
    print("=" * 60)
    print("\nThis will DELETE:")
    print("  - All events from events_data.json")
    print("  - All photos from uploads folder")
    print("  - All photos from processed folder")
    print("  - Face recognition data")
    print("\n⚠️  WARNING: THIS CANNOT BE UNDONE! ⚠️\n")
    
    confirm = input("Type 'DELETE ALL' to confirm: ")
    
    if confirm != "DELETE ALL":
        print("\n❌ Cleanup cancelled.")
        return
    
    print("\n🗑️  Starting cleanup...\n")
    
    # 1. Clear events_data.json
    try:
        if os.path.exists(events_data_path):
            with open(events_data_path, 'w') as f:
                json.dump([], f)
            print("✅ Cleared events_data.json")
        else:
            print("ℹ️  events_data.json not found")
    except Exception as e:
        print(f"❌ Error clearing events_data.json: {e}")
    
    # 2. Delete all uploads
    try:
        if os.path.exists(uploads_folder):
            for item in os.listdir(uploads_folder):
                item_path = os.path.join(uploads_folder, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"✅ Deleted uploads/{item}")
                elif os.path.isfile(item_path):
                    os.remove(item_path)
                    print(f"✅ Deleted uploads/{item}")
            print("✅ Cleared uploads folder")
        else:
            print("ℹ️  uploads folder not found")
    except Exception as e:
        print(f"❌ Error clearing uploads: {e}")
    
    # 3. Delete all processed photos
    try:
        if os.path.exists(processed_folder):
            for item in os.listdir(processed_folder):
                item_path = os.path.join(processed_folder, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"✅ Deleted processed/{item}")
                elif os.path.isfile(item_path):
                    os.remove(item_path)
                    print(f"✅ Deleted processed/{item}")
            print("✅ Cleared processed folder")
        else:
            print("ℹ️  processed folder not found")
    except Exception as e:
        print(f"❌ Error clearing processed: {e}")
    
    # 4. Delete face recognition data
    try:
        if os.path.exists(known_faces_path):
            os.remove(known_faces_path)
            print("✅ Deleted known_faces.dat")
        else:
            print("ℹ️  known_faces.dat not found")
    except Exception as e:
        print(f"❌ Error deleting known_faces.dat: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Cleanup complete!")
    print("=" * 60)
    print("\nYou can now:")
    print("  1. Rebuild Docker: docker build -t picme-app .")
    print("  2. Start fresh: docker run -d -p 8080:8080 ...")
    print("  3. Create new events and upload photos")
    print("\n")

if __name__ == "__main__":
    cleanup_all_data()
