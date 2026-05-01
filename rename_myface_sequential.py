#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

def rename_myface_sequential():
    """Rename all files in myface directory to sequential photo1, photo2, etc. format"""
    
    myface_dir = Path("/Users/victorkhudyakov/dutin/myface")
    
    if not myface_dir.exists():
        print(f"Directory {myface_dir} does not exist!")
        return
    
    # Get all files in the directory (excluding backup and log files)
    files = []
    for file_path in myface_dir.iterdir():
        if file_path.is_file() and not file_path.name.endswith(('.txt', '.log')):
            files.append(file_path)
    
    # Sort files by modification time to get a consistent order
    files.sort(key=lambda x: x.stat().st_mtime)
    
    print(f"Found {len(files)} files to rename")
    
    # Create a backup of current names
    with open(myface_dir / "sequential_rename_backup.txt", "w") as backup_file:
        for file_path in files:
            backup_file.write(f"{file_path.name}\n")
    
    # Rename files to photo1, photo2, etc. with proper extensions
    counter = 1
    renamed_files = []
    
    for file_path in files:
        # Get file extension
        extension = file_path.suffix.lower()
        
        # New name
        new_name = f"photo{counter}{extension}"
        new_path = myface_dir / new_name
        
        # If target file exists, find next available number
        while new_path.exists():
            counter += 1
            new_name = f"photo{counter}{extension}"
            new_path = myface_dir / new_name
        
        # Skip if file already has the correct name
        if file_path.name == new_name:
            print(f"Skipping {file_path.name} - already has correct name")
            counter += 1
            continue
        
        # Rename the file
        try:
            shutil.move(str(file_path), str(new_path))
            renamed_files.append((file_path.name, new_name))
            print(f"Renamed: {file_path.name} -> {new_name}")
            counter += 1
        except Exception as e:
            print(f"Error renaming {file_path.name}: {e}")
    
    # Save rename log
    with open(myface_dir / "sequential_rename_log.txt", "w") as log_file:
        log_file.write("Sequential File Rename Log\n")
        log_file.write("=" * 50 + "\n")
        for old_name, new_name in renamed_files:
            log_file.write(f"{old_name} -> {new_name}\n")
    
    print(f"\nRenamed {len(renamed_files)} files")
    print(f"Backup saved to: sequential_rename_backup.txt")
    print(f"Rename log saved to: sequential_rename_log.txt")

if __name__ == "__main__":
    rename_myface_sequential()
