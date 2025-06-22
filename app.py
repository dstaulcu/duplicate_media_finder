import streamlit as st
import os
import hashlib
import psutil
from PIL import Image
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import yaml
import fnmatch
import time

# Disk-friendly settings to prevent drive overload
DISK_FRIENDLY_MODE = True
MAX_CONCURRENT_READS = 2  # Limit simultaneous file reads (down from default 5+)
READ_DELAY_MS = 50  # Small delay between intensive operations
CHUNK_READ_DELAY_MS = 10  # Delay between file chunks

# Default media extensions
DEFAULT_MEDIA_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.mp4', '.mov', '.avi', '.mkv', '.heic']

# Default folders to skip on Windows (supports wildcards)
DEFAULT_SKIP_FOLDERS = [
    r'C:\\Windows',
    r'C:\\Program Files*',
    r'C:\\ProgramData',
    r'C:\\$Recycle.Bin',
    r'C:\\System Volume Information',
    r'C:\\Recovery',
    r'C:\\PerfLogs',
    r'C:\\Users\\*\\AppData',
    r'*\\node_modules',
    r'*\\.git',
    r'*\\.svn',
    r'*\\.hg',
    r'*\\__pycache__',
    r'*\\.vscode',
    r'*\\.idea',
    r'*\\temp',
    r'*\\tmp',
    r'*\\cache',
    r'*\\logs',
    r'*\\images',
    r'*\\pkgs',
    r'*\\envs',
    r'*\\.conda',
    r'*\\Lib'
]

def get_logical_drives():
    return [part.mountpoint for part in psutil.disk_partitions() if os.name == 'nt']

def find_media_files(drives, media_extensions, progress_callback=None, skip_folders=None, pause_check=None):
    if skip_folders is None:
        skip_folders = []
    
    def should_skip_folder(folder_path, skip_patterns):
        """Check if folder should be skipped based on wildcard patterns"""
        normalized_path = os.path.normpath(folder_path).replace('/', '\\')
        for pattern in skip_patterns:
            normalized_pattern = os.path.normpath(pattern).replace('/', '\\')
            if fnmatch.fnmatch(normalized_path, normalized_pattern):
                return True
            # Also check if pattern matches any parent path
            if fnmatch.fnmatch(normalized_path.lower(), normalized_pattern.lower()):
                return True
        return False
    
    # Resume from previous scan if available
    if 'scan_state' in st.session_state and st.session_state.get('scan_paused', False):
        media_files = st.session_state['scan_state'].get('media_files', [])
        processed_dirs = st.session_state['scan_state'].get('processed_dirs', 0)
        total_dirs = st.session_state['scan_state'].get('total_dirs', 0)
        remaining_walks = st.session_state['scan_state'].get('remaining_walks', [])
    else:
        media_files = []
        processed_dirs = 0
        
        # First pass: count total directories
        total_dirs = 0
        remaining_walks = []
        for drive in drives:
            for root, dirs, files in os.walk(drive):
                # Check if current directory should be skipped
                if should_skip_folder(root, skip_folders):
                    dirs.clear()  # Don't traverse subdirectories
                    continue
                total_dirs += 1
                remaining_walks.append((root, dirs.copy(), files.copy()))
    
    # Second pass: process files with pause support
    for root, dirs, files in remaining_walks[processed_dirs:]:
        # Check for pause request
        if pause_check and pause_check():
            # Save current state for resume
            st.session_state['scan_state'] = {
                'media_files': media_files,
                'processed_dirs': processed_dirs,
                'total_dirs': total_dirs,
                'remaining_walks': remaining_walks
            }
            st.session_state['scan_paused'] = True
            return media_files, False  # Return current results and not-complete flag
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in media_extensions:
                media_files.append(os.path.join(root, file))
        processed_dirs += 1
        if progress_callback:
            progress_callback(processed_dirs, total_dirs)
    
    # Scan completed successfully
    if 'scan_state' in st.session_state:
        del st.session_state['scan_state']
    st.session_state['scan_paused'] = False
    return media_files, True  # Return results and complete flag

def md5_checksum(file_path, chunk_size=8192):
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        return None

def chunk_reader(fobj, chunk_size=1024*1024):
    while True:
        chunk = fobj.read(chunk_size)
        if not chunk:
            break
        yield chunk

def get_quick_hash(file_path, chunk_size=1024*1024):
    """Get a quick hash using first + middle + last chunks for large files"""
    try:
        size = os.path.getsize(file_path)
        
        # For small files (< 3MB), use full hash
        if size < chunk_size * 3:
            return get_md5(file_path)
        
        # For large files, hash first + middle + last chunks
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            # First chunk
            first_chunk = f.read(chunk_size)
            hash_md5.update(first_chunk)
            
            # Middle chunk
            f.seek(size // 2)
            middle_chunk = f.read(chunk_size)
            hash_md5.update(middle_chunk)
            
            # Last chunk
            f.seek(-chunk_size, 2)
            last_chunk = f.read(chunk_size)
            hash_md5.update(last_chunk)
        
        return hash_md5.hexdigest()
    except Exception:
        return None

def get_quick_hash_safe(file_path, chunk_size=1024*1024):
    """Disk-friendly version of get_quick_hash with delays to prevent drive overload"""
    try:
        # Add small delay before file operation
        if DISK_FRIENDLY_MODE:
            time.sleep(CHUNK_READ_DELAY_MS / 1000.0)
            
        size = os.path.getsize(file_path)
        
        # For small files (< 3MB), use full hash
        if size < chunk_size * 3:
            return get_md5_safe(file_path)
        
        # For large files, hash first + middle + last chunks with delays
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            # First chunk
            first_chunk = f.read(chunk_size)
            hash_md5.update(first_chunk)
            
            if DISK_FRIENDLY_MODE:
                time.sleep(CHUNK_READ_DELAY_MS / 1000.0)
            
            # Middle chunk
            f.seek(size // 2)
            middle_chunk = f.read(chunk_size)
            hash_md5.update(middle_chunk)
            
            if DISK_FRIENDLY_MODE:
                time.sleep(CHUNK_READ_DELAY_MS / 1000.0)
            
            # Last chunk
            f.seek(-chunk_size, 2)
            last_chunk = f.read(chunk_size)
            hash_md5.update(last_chunk)
        
        return hash_md5.hexdigest()
    except Exception:
        return None

def get_md5(file_path):
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in chunk_reader(f):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None

def get_md5_safe(file_path):
    """Disk-friendly version of get_md5 with progress delays"""
    try:
        hash_md5 = hashlib.md5()
        chunk_count = 0
        
        with open(file_path, "rb") as f:
            for chunk in chunk_reader(f):
                hash_md5.update(chunk)
                chunk_count += 1
                
                # Add delay every 10 chunks to prevent disk thrashing
                if DISK_FRIENDLY_MODE and chunk_count % 10 == 0:
                    time.sleep(CHUNK_READ_DELAY_MS / 1000.0)
                    
        return hash_md5.hexdigest()
    except Exception:
        return None

def group_by_size(file_paths):
    size_dict = {}
    for path in file_paths:
        try:
            size = os.path.getsize(path)
            size_dict.setdefault(size, []).append(path)
        except Exception:
            continue
    return size_dict

def find_potential_duplicates(file_paths):
    # First pass: group by size
    size_groups = group_by_size(file_paths)
    # Only keep groups with more than one file
    potential_dupes = [group for group in size_groups.values() if len(group) > 1]
    return [item for sublist in potential_dupes for item in sublist]

def compute_quick_hashes(file_paths, progress_callback=None, max_workers=None):
    """Compute quick hashes for initial duplicate detection - disk-friendly version"""
    if max_workers is None:
        max_workers = MAX_CONCURRENT_READS if DISK_FRIENDLY_MODE else 4
        
    quick_hashes = {}
    total = len(file_paths)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(get_quick_hash_safe, f): f for f in file_paths}
        for i, future in enumerate(future_to_file):
            file = future_to_file[future]
            try:
                quick_hash = future.result()
                if quick_hash:
                    quick_hashes[file] = quick_hash
                    
                # Add small delay to prevent disk overload
                if DISK_FRIENDLY_MODE and i % 10 == 0:  # Every 10 files
                    time.sleep(READ_DELAY_MS / 1000.0)
            except Exception:
                continue
            if progress_callback:
                progress_callback(i + 1, total, "Quick hashing")
    return quick_hashes

def compute_quick_hashes_pausable(file_paths, progress_callback=None, max_workers=None, pause_check=None):
    """Compute quick hashes for initial duplicate detection with pause support - disk-friendly version"""
    if max_workers is None:
        max_workers = MAX_CONCURRENT_READS if DISK_FRIENDLY_MODE else 4
        
    quick_hashes = {}
    total = len(file_paths)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(get_quick_hash_safe, f): f for f in file_paths}
        for i, future in enumerate(future_to_file):
            # Check for pause request
            if pause_check and pause_check():
                # Cancel remaining futures
                for remaining_future in future_to_file:
                    if not remaining_future.done():
                        remaining_future.cancel()
                break
                
            file = future_to_file[future]
            try:
                quick_hash = future.result()
                if quick_hash:
                    quick_hashes[file] = quick_hash
                    
                # Add small delay to prevent disk overload
                if DISK_FRIENDLY_MODE and i % 10 == 0:  # Every 10 files
                    time.sleep(READ_DELAY_MS / 1000.0)
            except Exception:
                continue
            if progress_callback:
                progress_callback(i + 1, total, "Quick hashing")
    return quick_hashes

def compute_full_checksums(file_paths, progress_callback=None, max_workers=None):
    """Compute full MD5 checksums for final verification - disk-safe version"""
    if max_workers is None:
        max_workers = MAX_CONCURRENT_READS if DISK_FRIENDLY_MODE else 4
        
    checksums = {}
    total = len(file_paths)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(get_md5_safe, f): f for f in file_paths}
        for i, future in enumerate(future_to_file):
            file = future_to_file[future]
            try:
                checksum = future.result()
                if checksum:
                    checksums[file] = checksum
                    
                # Add small delay to prevent disk overload
                if DISK_FRIENDLY_MODE and i % 5 == 0:  # Every 5 files  
                    time.sleep(READ_DELAY_MS / 1000.0)
                    
            except Exception:
                continue
            if progress_callback:
                progress_callback(i + 1, total, "Full checksumming")
    return checksums

def compute_full_checksums_pausable(file_paths, progress_callback=None, max_workers=None, pause_check=None):
    """Compute full MD5 checksums for final verification with pause support - disk-safe version"""
    if max_workers is None:
        max_workers = MAX_CONCURRENT_READS if DISK_FRIENDLY_MODE else 4
        
    checksums = {}
    total = len(file_paths)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(get_md5_safe, f): f for f in file_paths}
        for i, future in enumerate(future_to_file):
            # Check for pause request
            if pause_check and pause_check():
                # Cancel remaining futures
                for remaining_future in future_to_file:
                    if not remaining_future.done():
                        remaining_future.cancel()
                break
                
            file = future_to_file[future]
            try:
                checksum = future.result()
                if checksum:
                    checksums[file] = checksum
                    
                # Add small delay to prevent disk overload
                if DISK_FRIENDLY_MODE and i % 5 == 0:  # Every 5 files  
                    time.sleep(READ_DELAY_MS / 1000.0)
                    
            except Exception:
                continue
            if progress_callback:
                progress_callback(i + 1, total, "Full checksumming")
    return checksums

def group_by_checksum_multistage(files, progress_callback=None, max_workers=None, pause_check=None, high_precision_mode=False):
    """Multi-stage duplicate detection: Size -> Quick Hash -> Full Hash (disk-safe version)
    
    Args:
        files: List of file paths to check for duplicates
        progress_callback: Function to report progress
        max_workers: Maximum number of concurrent threads
        pause_check: Function that returns True if operation should pause
        high_precision_mode: If True, performs full MD5; if False, uses quick hash only
    """
    
    # Use disk-friendly settings
    if max_workers is None:
        max_workers = MAX_CONCURRENT_READS if DISK_FRIENDLY_MODE else 4
    
    # Adjust progress stages based on precision mode
    total_stages = 3 if high_precision_mode else 2
    
    # Check for pause before starting
    if pause_check and pause_check():
        return {}
    
    # Stage 1: Group by file size (instant)
    if progress_callback:
        progress_callback(0, total_stages, "Stage 1: Grouping by size...")
    
    size_groups = group_by_size(files)
    potential_dupes_by_size = []
    for group in size_groups.values():
        if len(group) > 1:
            potential_dupes_by_size.extend(group)
    
    if not potential_dupes_by_size:
        return {}
    
    if progress_callback:
        progress_callback(1, total_stages, f"Stage 1 complete: {len(potential_dupes_by_size)} potential duplicates by size")
    
    # Check for pause after stage 1
    if pause_check and pause_check():
        return {}
    
    # Stage 2: Quick hash for size-matched files
    if progress_callback:
        progress_callback(1, total_stages, "Stage 2: Computing quick hashes")
    
    def quick_progress(done, total, stage):
        if progress_callback:
            progress_callback(1 + (done/total), total_stages, f"Stage 2: Quick hashing {done}/{total}")
    
    quick_hashes = compute_quick_hashes_pausable(potential_dupes_by_size, quick_progress, max_workers, pause_check)
    
    # Check if paused during quick hashing
    if pause_check and pause_check():
        return {}
      # Group by quick hash
    quick_hash_groups = {}
    for file, quick_hash in quick_hashes.items():
        quick_hash_groups.setdefault(quick_hash, []).append(file)
    
    # Find files that have matching quick hashes
    final_candidates = []
    for group in quick_hash_groups.values():
        if len(group) > 1:
            final_candidates.extend(group)
    
    if not final_candidates:
        return {}
    
    if progress_callback:
        progress_callback(2, total_stages, f"Stage 2 complete: {len(final_candidates)} candidates found")
    
    # Check for pause after stage 2
    if pause_check and pause_check():
        return {}
    
    # Stage 3: Full MD5 (only if high precision mode is enabled)
    if high_precision_mode:
        if progress_callback:
            progress_callback(2, total_stages, "Stage 3: Computing full checksums")
        
        def full_progress(done, total, stage):
            if progress_callback:
                progress_callback(2 + (done/total), total_stages, f"Stage 3: Full checksumming {done}/{total}")
        
        full_checksums = compute_full_checksums_pausable(final_candidates, full_progress, max_workers, pause_check)
        
        # Check if paused during full checksumming
        if pause_check and pause_check():
            return {}
        
        # Final grouping by full checksum
        checksum_map = {}
        for file, checksum in full_checksums.items():
            checksum_map.setdefault(checksum, []).append(file)
    else:
        # Use quick hash as final result (much faster, still very reliable for media files)
        checksum_map = quick_hash_groups
    
    result = {k: v for k, v in checksum_map.items() if len(v) > 1}
    
    if progress_callback:
        total_duplicates = sum(len(v) for v in result.values())
        mode_desc = "High Precision" if high_precision_mode else "Quick Hash"
        progress_callback(total_stages, total_stages, f"Complete: Found {total_duplicates} duplicate files ({mode_desc} mode)")
    
    return result

def show_image_preview(file_path):
    try:
        img = Image.open(file_path)
        st.image(img, caption=os.path.basename(file_path), use_column_width=True)
    except Exception:
        st.write(f"Cannot preview: {file_path}")

# Settings file path
def get_settings_path():
    return os.path.join(os.path.dirname(__file__), 'settings.yaml')

def load_settings():
    path = get_settings_path()
    if os.path.exists(path):
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    return {}

def save_settings(settings):
    path = get_settings_path()
    with open(path, 'w') as f:
        yaml.safe_dump(settings, f)

def main():
    # Configure page settings
    st.set_page_config(
        page_title="Duplicate Media Finder",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("Duplicate Media Finder")
    st.write("Scan drives or folders for duplicate media files and annotate a listing for external review or action.")
    
    # Load settings
    settings = load_settings()
    
    # Sidebar layout improvements
    with st.sidebar:
        # Discovery Mode - Always visible
        st.header("📂 Discovery Mode")
        # Make 'Folders' the first option and default
        mode = st.radio("Choose how to scan:", ["Folders", "Drives"], index=0)
        
        # Scan Targets - Always visible
        st.markdown("---")
        st.header("🎯 Scan Targets")
        drives = get_logical_drives()
        selected_drives = []
        selected_folders = []
        mock_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'mock_media'))
        if mode == "Drives":
            st.write("Discovered Drives:")
            selected_drives = st.multiselect("Select drives to scan", drives, default=drives)
        else:
            default_folders = mock_path
            selected_folders = st.text_area(
                "Enter folder paths to scan (one per line)",
                value=default_folders
            ).splitlines()
            selected_folders = [f.strip() for f in selected_folders if f.strip()]          # Advanced settings - Collapsible
        st.markdown("---")
        
        with st.expander("⚙️ Advanced Settings", expanded=False):
            st.header("File Types")
            if 'file_types' in settings:
                default_filetypes = ','.join(settings['file_types'])
            else:
                default_filetypes = ','.join(DEFAULT_MEDIA_EXTENSIONS)
            media_ext_input = st.text_input(
                "File extensions to process (comma-separated, e.g. .jpg,.png,.mp4)",
                value=default_filetypes
            )
            media_extensions = set([e.strip().lower() for e in media_ext_input.split(',') if e.strip()])
            st.markdown("---")
            st.header("Skip Folders (Wildcards Supported)")
            if 'skip_folders' in settings:
                default_skip_folders = '\n'.join(settings['skip_folders'])
            else:
                default_skip_folders = '\n'.join(DEFAULT_SKIP_FOLDERS)
            skip_folders_input = st.text_area(
                "Skip these folders (one per line, wildcards supported)",
                value=default_skip_folders,
                help="Examples: C:\\Users\\*\\AppData, *\\node_modules, C:\\Program Files*"            )
            skip_folders = [f.strip() for f in skip_folders_input.splitlines() if f.strip()]
            
            st.markdown("---")
            st.header("Duplicate Detection Mode")
            
            # High Precision Mode setting
            high_precision = st.checkbox(
                "🎯 High Precision Mode (Full MD5)",
                value=settings.get('high_precision_mode', False),
                help="Enable full MD5 checksums for 100% accuracy. ⚠️ WARNING: This can take much longer and may stress drives with large collections."
            )
            
            if not high_precision:
                st.info("ℹ️ **Quick Hash Mode** (Default): Uses first + middle + last 1MB of each file. Extremely reliable for media files with dramatically faster performance.")
            else:
                st.warning("⚠️ **High Precision Mode**: Computes full MD5 checksums. Provides 100% certainty but may take hours and stress drives with large video collections.")
        
        st.markdown("---")
        st.header("🚀 Actions")
        
        # Show appropriate buttons based on scan state
        if st.session_state.get('scan_paused', False):
            col1, col2 = st.columns(2)
            with col1:
                resume_clicked = st.button("▶️ Resume Scan", type="primary")
            with col2:
                cancel_clicked = st.button("❌ Cancel Scan", type="secondary")
        elif st.session_state.get('scanning', False):
            pause_clicked = st.button("⏸️ Pause Scan", type="secondary")
        else:
            inventory_clicked = st.button("📁 Inventory Media Files", type="primary")
      # Save settings if changed
    if (set(media_extensions) != set(settings.get('file_types', [])) or 
        skip_folders != settings.get('skip_folders', []) or
        high_precision != settings.get('high_precision_mode', False)):
        settings['file_types'] = list(media_extensions)
        settings['skip_folders'] = skip_folders
        settings['high_precision_mode'] = high_precision
        save_settings(settings)# Handle pause/resume/cancel logic
    if st.session_state.get('scan_paused', False):
        # Resume scan
        if 'resume_clicked' in locals() and resume_clicked:
            st.session_state['scanning'] = True
            st.session_state['scan_paused'] = False
            st.rerun()
        # Cancel scan
        elif 'cancel_clicked' in locals() and cancel_clicked:
            if 'scan_state' in st.session_state:
                del st.session_state['scan_state']
            st.session_state['scan_paused'] = False
            st.session_state['scanning'] = False
            st.success("Scan cancelled.")
            st.rerun()
    
    # Handle pause request during scanning
    if st.session_state.get('scanning', False) and 'pause_clicked' in locals() and pause_clicked:
        st.session_state['scan_pause_requested'] = True
        st.info("Pause requested. Scan will pause at the next safe point...")
    
    # Inventory - Start new scan
    if 'inventory_clicked' in locals() and inventory_clicked:
        # Clear prior results from session state
        st.session_state['media_files'] = []
        st.session_state['duplicates'] = {}
        st.session_state['annotations'] = {}
        st.session_state['scanning'] = True
        st.session_state['scan_paused'] = False
        st.session_state['scan_pause_requested'] = False
        if 'scan_state' in st.session_state:
            del st.session_state['scan_state']
        
        if mode == "Drives" and not selected_drives:
            st.session_state['scanning'] = False
            st.warning("Please select at least one drive.")
        elif mode == "Folders" and not selected_folders:
            st.session_state['scanning'] = False
            st.warning("Please enter at least one folder path.")
        else:
            st.rerun()  # Refresh to show scanning state
    
    # Active scanning process
    if st.session_state.get('scanning', False) and not st.session_state.get('scan_paused', False):
        st.info("🔍 Scanning in progress... Use the pause button in the sidebar to pause.")
        
        with st.spinner("Scanning for media files..."):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def progress_callback(done, total):
                progress_bar.progress(min(done / total, 1.0))
                status_text.text(f"Scanning folder {done} of {total}")
            
            def pause_check():
                return st.session_state.get('scan_pause_requested', False)
            
            scan_targets = selected_drives if mode == "Drives" else selected_folders
            result = find_media_files(scan_targets, media_extensions, progress_callback, skip_folders, pause_check)
            
            if isinstance(result, tuple):
                files, scan_complete = result
            else:
                files, scan_complete = result, True
            
            if scan_complete:
                st.session_state['media_files'] = files
                st.session_state['scanning'] = False
                st.session_state['scan_paused'] = False
                progress_bar.empty()
                status_text.empty()
                st.success(f"✅ Scan complete! Found {len(files)} media files.")
                st.rerun()
            else:
                # Scan was paused
                st.session_state['media_files'] = files  # Save partial results
                st.session_state['scanning'] = False
                st.session_state['scan_paused'] = True
                st.session_state['scan_pause_requested'] = False
                progress_bar.empty()
                status_text.empty()
                st.warning(f"⏸️ Scan paused. Found {len(files)} files so far. Use Resume to continue.")
                st.rerun()    # Find duplicates
    if 'media_files' in st.session_state and len(st.session_state['media_files']) > 0:
        if not st.session_state.get('scanning', False) and not st.session_state.get('scan_paused', False):
            if st.button("🔍 Find Duplicates"):
                st.session_state['duplicate_scanning'] = True
                st.session_state['duplicate_pause_requested'] = False
                st.rerun()
          # Handle duplicate scanning pause request
        if st.session_state.get('duplicate_scanning', False):
            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button("⏸️ Pause Duplicate Detection"):
                    st.session_state['duplicate_pause_requested'] = True
                    st.info("Pause requested. Will pause at the next safe point...")
            
            with st.spinner("Calculating checksums and finding duplicates..."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def progress_callback(done, total, message="Processing"):
                    progress_bar.progress(min(done / total, 1.0))
                    status_text.text(message)
                
                def pause_check():
                    return st.session_state.get('duplicate_pause_requested', False)
                
                dupes = group_by_checksum_multistage(
                    st.session_state['media_files'], 
                    progress_callback, 
                    max_workers=8, 
                    pause_check=pause_check,
                    high_precision_mode=settings.get('high_precision_mode', False)
                )
                
                if st.session_state.get('duplicate_pause_requested', False):
                    st.session_state['duplicate_scanning'] = False
                    st.session_state['duplicate_pause_requested'] = False
                    progress_bar.empty()
                    status_text.empty()
                    st.warning("⏸️ Duplicate detection paused. Click 'Find Duplicates' to restart.")
                else:
                    st.session_state['duplicates'] = dupes
                    st.session_state['annotations'] = {}
                    st.session_state['duplicate_scanning'] = False
                    progress_bar.empty()
                    status_text.empty()
                    total_duplicates = sum(len(v) for v in dupes.values())
                    st.success(f"✅ Found {total_duplicates} duplicate files.")
                
                st.rerun()

    # Only show results if there are any and not scanning
    if (st.session_state.get('media_files') and 
        len(st.session_state['media_files']) > 0 and 
        not st.session_state.get('scanning', False) and 
        not st.session_state.get('duplicate_scanning', False)):
        
        if 'duplicates' in st.session_state:
            st.header("Duplicate Groups Table View")
              # Build table data with caching to improve performance
            cache_key = f"table_data_{len(st.session_state['duplicates'])}"
            if cache_key not in st.session_state or st.session_state.get('annotations_changed', True):
                table_rows = []
                # Cache file sizes to avoid repeated os.path.getsize calls
                file_sizes = st.session_state.get('file_sizes_cache', {})
                
                for checksum, files in st.session_state['duplicates'].items():
                    for file in files:
                        if file not in file_sizes:
                            file_sizes[file] = os.path.getsize(file) if os.path.exists(file) else 0
                        
                        size = file_sizes[file]
                        ext = os.path.splitext(file)[1].lower()
                        annotation = st.session_state['annotations'].get(file, "None")
                        table_rows.append({
                            "full_path": file,
                            "size": size,
                            "file_type": ext,
                            "checksum": checksum,
                            "annotation": annotation
                        })
                
                st.session_state['file_sizes_cache'] = file_sizes
                df = pd.DataFrame(table_rows)
                st.session_state[cache_key] = df
                st.session_state['annotations_changed'] = False
            else:
                df = st.session_state[cache_key].copy()
                # Update annotations from session state
                for idx, row in df.iterrows():
                    df.at[idx, 'annotation'] = st.session_state['annotations'].get(row['full_path'], "None")
            # Add disposition selectbox per row
            if not df.empty:
                st.set_page_config(layout="wide")                # Add column for duplicate file paths (optimized)
                def get_other_duplicates(row, df):
                    same_checksum = df[(df['checksum'] == row['checksum']) & (df['full_path'] != row['full_path'])]
                    return '; '.join(same_checksum['full_path'].tolist())
                
                # Only compute duplicate_of column if not already computed or if data changed
                if 'duplicate_of' not in df.columns or st.session_state.get('duplicates_changed', True):
                    df['duplicate_of'] = df.apply(lambda row: get_other_duplicates(row, df), axis=1)
                    st.session_state['duplicates_changed'] = False

                filter_disp = st.selectbox("Filter by annotation", ["All"] + ["None", "Keep", "Delete", "Move", "Review", "Deleted"])
                filtered_df = df if filter_disp == "All" else df[df['annotation'] == filter_disp]
                
                # Initialize selection column - only one row can be selected at a time
                filtered_df = filtered_df.copy()
                filtered_df['select'] = False
                
                # Get current selection index, default to 0 if none selected
                current_selection = st.session_state.get('selected_row_idx', 0)
                if current_selection < len(filtered_df):
                    filtered_df.iloc[current_selection, filtered_df.columns.get_loc('select')] = True
                else:
                    # Reset to first row if current selection is out of bounds
                    current_selection = 0
                    if len(filtered_df) > 0:
                        filtered_df.iloc[0, filtered_df.columns.get_loc('select')] = True
                    st.session_state['selected_row_idx'] = current_selection
                
                # Configure column widths and text wrapping
                column_config = {
                    "select": st.column_config.CheckboxColumn(
                        "Select",
                        width="small",
                        help="Select file for actions (only one at a time)"
                    ),
                    "full_path": st.column_config.TextColumn(
                        "Full Path",
                        width="large",
                        help="Full path to the file"
                    ),
                    "duplicate_of": st.column_config.TextColumn(
                        "Duplicate Of",
                        width="large",
                        help="Other files with the same checksum"
                    )
                }
                
                # Display table with single checkbox selection
                edited_df = st.data_editor(
                    filtered_df[["select", "full_path", "size", "file_type", "checksum", "annotation", "duplicate_of"]],
                    use_container_width=True,
                    hide_index=True,
                    key="dupes_table",
                    num_rows="fixed",  # Prevents adding/deleting rows
                    disabled=["full_path", "size", "file_type", "checksum", "annotation", "duplicate_of"],  # Only checkbox is editable
                    column_config=column_config
                )
                
                # Handle selection changes and enforce single selection
                selected_indices = edited_df[edited_df['select'] == True].index.tolist()
                
                if len(selected_indices) > 1:
                    # Multiple selections detected - keep only the most recent one
                    # This handles the case where user clicks multiple checkboxes rapidly
                    new_selection = selected_indices[-1]  # Keep the last selected
                    st.session_state['selected_row_idx'] = new_selection
                    st.rerun()  # Refresh to show correct selection
                elif len(selected_indices) == 1:
                    # Single selection - update session state
                    st.session_state['selected_row_idx'] = selected_indices[0]
                elif len(selected_indices) == 0:
                    # No selection - default to first row
                    if len(filtered_df) > 0:
                        st.session_state['selected_row_idx'] = 0
                        st.rerun()  # Refresh to show selection
                
                # Get the currently selected row
                selected_row_idx = st.session_state.get('selected_row_idx', 0)
                if selected_row_idx < len(filtered_df):
                    selected_row = filtered_df.iloc[selected_row_idx]
                      # Display selected file information
                    file_name = os.path.basename(selected_row['full_path'])
                    st.markdown("---")
                    st.markdown(f"### 🎯 Selected File: `{file_name}`")
                    st.markdown(f"**📁 Full Path:** `{selected_row['full_path']}`")
                    
                    # Show duplicate files for the selected file
                    selected_checksum = selected_row['checksum']
                    if selected_checksum in st.session_state['duplicates']:
                        duplicate_files = st.session_state['duplicates'][selected_checksum]
                        # Remove the selected file from the list to avoid showing it twice
                        other_duplicates = [f for f in duplicate_files if f != selected_row['full_path']]
                        
                        if other_duplicates:
                            st.markdown(f"**🔗 Duplicate Files ({len(other_duplicates)} other{'s' if len(other_duplicates) != 1 else ''}):**")
                            for i, dup_file in enumerate(other_duplicates, 1):
                                dup_name = os.path.basename(dup_file)
                                dup_annotation = st.session_state['annotations'].get(dup_file, "None")
                                annotation_badge = f" `{dup_annotation}`" if dup_annotation != "None" else ""
                                st.markdown(f"   {i}. `{dup_name}`{annotation_badge}")
                                st.markdown(f"      📁 `{dup_file}`")
                        else:
                            st.markdown("**🔗 Duplicate Files:** *(This is the only file with this checksum)*")
                    else:
                        st.markdown("**🔗 Duplicate Files:** *(No duplicates found - this shouldn't happen)*")
                    
                    # Action buttons for the selected file
                    col1, col2, col3 = st.columns([1,1,1])
                    with col1:
                        if st.button("🔍 Open in Viewer", help="Open file in default application"):
                            try:
                                os.startfile(selected_row['full_path'])
                                st.success(f"Opened {file_name}")
                            except Exception as e:
                                st.error(f"Could not open file: {e}")
                    with col2:
                        if st.button("📁 Open Folder", help="Open containing folder"):
                            try:
                                folder = os.path.dirname(selected_row['full_path'])
                                os.startfile(folder)
                                st.success(f"Opened folder")
                            except Exception as e:
                                st.error(f"Could not open folder: {e}")
                    with col3:                        # Delete file button with confirmation
                        if st.button("🗑️ Delete File", help="Permanently delete this file", type="secondary"):
                            st.session_state[f'confirm_delete_{selected_row_idx}'] = True
                    
                    # Annotation selector in a separate row below action buttons
                    st.markdown("**Annotation:**")
                    disposition_options = ["None", "Keep", "Delete", "Move", "Review", "Ignore Folder"]
                    current_disposition = selected_row['annotation'] if selected_row['annotation'] in disposition_options else "None"
                    key = f"annotate_{selected_row['full_path']}"
                    
                    new_disp = st.selectbox(
                        f"📝 Annotate for Review",
                        disposition_options,
                        key=key,
                        index=disposition_options.index(current_disposition),
                        help="Mark this file for future action (annotation only - does not perform the action)"
                    )
                    
                    # Update annotation if changed and force table refresh
                    if new_disp != current_disposition:
                        # Update session state annotations immediately
                        st.session_state['annotations'][selected_row['full_path']] = new_disp
                        
                        # Force table refresh by invalidating cache
                        cache_key = f"table_data_{len(st.session_state['duplicates'])}"
                        if cache_key in st.session_state:
                            del st.session_state[cache_key]
                        
                        # Handle 'Ignore Folder' annotation
                        if new_disp == "Ignore Folder":
                            folder = os.path.dirname(selected_row['full_path'])
                            if folder not in skip_folders:
                                skip_folders.append(folder)
                                settings['skip_folders'] = skip_folders
                                save_settings(settings)
                                st.warning("✅ Folder added to skip list. Please click 'Inventory Media Files' to refresh the table.")
                        else:
                            st.success(f"✅ Annotation set to '{new_disp}' for {file_name}")
                            st.rerun()  # Force immediate refresh
                    
                    # Show confirmation dialog if delete was clicked
                    if st.session_state.get(f'confirm_delete_{selected_row_idx}', False):
                            st.markdown("---")
                            st.error(f"⚠️ **CONFIRM DELETE**")
                            st.markdown(f"Are you sure you want to permanently delete:")
                            st.code(f"{selected_row['full_path']}")
                            st.markdown("**This action cannot be undone!**")
                            
                            col_confirm, col_cancel = st.columns(2)
                            with col_confirm:
                                if st.button("✅ Yes, Delete", type="primary", key=f"confirm_yes_{selected_row_idx}"):
                                    try:
                                        # Verify file still exists before deletion
                                        if os.path.exists(selected_row['full_path']):
                                            os.remove(selected_row['full_path'])
                                            st.success(f"✅ File deleted successfully: {file_name}")
                                            
                                            # Update annotations to mark as deleted
                                            st.session_state['annotations'][selected_row['full_path']] = "Deleted"
                                            
                                            # Remove from current dataframe display
                                            df = df[df['full_path'] != selected_row['full_path']]
                                            
                                            # Clear confirmation state
                                            st.session_state[f'confirm_delete_{selected_row_idx}'] = False
                                            
                                            # Refresh the display
                                            st.rerun()
                                        else:
                                            st.error(f"❌ File not found: {selected_row['full_path']}")
                                            st.session_state[f'confirm_delete_{selected_row_idx}'] = False
                                    except Exception as e:
                                        st.error(f"❌ Error deleting file: {str(e)}")
                                        st.session_state[f'confirm_delete_{selected_row_idx}'] = False
                            
                            with col_cancel:
                                if st.button("❌ Cancel", key=f"confirm_no_{selected_row_idx}"):
                                    st.session_state[f'confirm_delete_{selected_row_idx}'] = False
                                    st.rerun()
                else:
                    st.warning("No files to display after filtering.")
            else:
                st.info("No duplicates found.")            # Export - Single consolidated download button
            export_df = df.copy()
            st.download_button(
                label="📥 Download Annotations CSV",
                data=export_df.to_csv(index=False),
                file_name="duplicate_media_annotations.csv",
                mime="text/csv",
                help="Download the duplicate file annotations as a CSV file"
            )
    elif st.session_state.get('scanning', False):
        with st.expander("Previous results (hidden during scan)", expanded=False):
            st.write("Previous results are hidden while scanning is in progress.")

if __name__ == "__main__":
    main()
