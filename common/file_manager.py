import os
import datetime
import zipfile
from flask import send_file

# --- Configuration ---
CAPTURES_DIR = "static/captures"
RECORDINGS_DIR = "static/recordings"
ALL_DIRS = [CAPTURES_DIR, RECORDINGS_DIR]

def get_file_list():
    """
    Scans the media directories and returns a dictionary of files,
    separated by type (images and videos).
    """
    file_data = {"images": [], "videos": []}
    
    for directory in ALL_DIRS:
        if not os.path.exists(directory):
            continue
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                try:
                    stat = os.stat(filepath)
                    file_info = {
                        "name": filename,
                        "path": filepath,
                        "size": round(stat.st_size / (1024 * 1024), 2),  # Size in MB
                        "modified_timestamp": stat.st_mtime,
                        "modified_date": datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    }
                    if directory == CAPTURES_DIR:
                        file_data["images"].append(file_info)
                    else:
                        file_data["videos"].append(file_info)

                except Exception as e:
                    print(f"WARN: Could not stat file {filepath}: {e}")

    # Sort files in each category by date, newest first
    file_data["images"].sort(key=lambda x: x['modified_timestamp'], reverse=True)
    file_data["videos"].sort(key=lambda x: x['modified_timestamp'], reverse=True)
    
    return file_data

def create_zip_archive(files_to_zip, zip_filename="archive.zip"):
    """
    Creates a zip archive from a list of file paths.
    """
    zip_filepath = os.path.join("static", zip_filename)
    with zipfile.ZipFile(zip_filepath, 'w') as zipf:
        for file_path in files_to_zip:
            if os.path.exists(file_path):
                zipf.write(file_path, os.path.basename(file_path))
            else:
                print(f"WARN: File not found for zipping: {file_path}")
    return zip_filepath

def delete_selected_files(files_to_delete):
    """
    Deletes a list of files from the server.
    """
    deleted_count = 0
    errors = []
    for file_path in files_to_delete:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted_count += 1
            else:
                errors.append(f"File not found: {file_path}")
        except Exception as e:
            errors.append(f"Error deleting {file_path}: {e}")
            
    return deleted_count, errors