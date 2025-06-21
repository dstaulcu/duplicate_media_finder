# Duplicate Media Finder

This Streamlit app inventories all media files on your logical drives, computes checksums, and helps you reconcile duplicates.

## Features
- Scan all logical drives for media files (images, videos, etc.)
- Compute MD5 checksums for each file
- Detect and display duplicate files
- Preview images and basic info for videos
- Choose which files to keep or delete/move

## Setup

1. Install dependencies:
   ```sh
   pip install streamlit pillow psutil send2trash
   ```

2. Run the app:
   ```sh
   streamlit run app.py
   ```

## Notes
- Deletions use send2trash for safety (files go to Recycle Bin).
- Scanning large drives may take time.
