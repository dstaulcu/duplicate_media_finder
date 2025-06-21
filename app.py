import streamlit as st
import os
import hashlib
import psutil
from PIL import Image
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import yaml

# Default media extensions
DEFAULT_MEDIA_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.mp4', '.mov', '.avi', '.mkv', '.heic']

# Default folders to skip on Windows
DEFAULT_SKIP_FOLDERS = [
    r'C:\\Windows',
    r'C:\\Program Files',
    r'C:\\Program Files (x86)',
    r'C:\\ProgramData',
    r'C:\\$Recycle.Bin',
    r'C:\\System Volume Information',
    r'C:\\Recovery',
    r'C:\\PerfLogs',
]

def get_logical_drives():
    return [part.mountpoint for part in psutil.disk_partitions() if os.name == 'nt']

def find_media_files(drives, media_extensions, progress_callback=None, skip_folders=None):
    if skip_folders is None:
        skip_folders = []
    skip_folders = [os.path.normpath(f) for f in skip_folders]
    media_files = []
    total_dirs = 0
    for drive in drives:
        for root, _, files in os.walk(drive):
            skip = False
            for skip_folder in skip_folders:
                if os.path.commonpath([os.path.normpath(root), skip_folder]) == skip_folder:
                    skip = True
                    break
            if skip:
                continue
            total_dirs += 1
    processed_dirs = 0
    for drive in drives:
        for root, _, files in os.walk(drive):
            skip = False
            for skip_folder in skip_folders:
                if os.path.commonpath([os.path.normpath(root), skip_folder]) == skip_folder:
                    skip = True
                    break
            if skip:
                continue
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in media_extensions:
                    media_files.append(os.path.join(root, file))
            processed_dirs += 1
            if progress_callback:
                progress_callback(processed_dirs, total_dirs)
    return media_files

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

def get_md5(file_path):
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in chunk_reader(f):
                hash_md5.update(chunk)
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

def compute_checksums(file_paths, progress_callback=None, max_workers=4):
    checksums = {}
    total = len(file_paths)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {executor.submit(get_md5, f): f for f in file_paths}
        for i, future in enumerate(future_to_file):
            file = future_to_file[future]
            try:
                checksum = future.result()
                if checksum:
                    checksums[file] = checksum
            except Exception:
                continue
            if progress_callback:
                progress_callback(i + 1, total)
    return checksums

def group_by_checksum_parallel(files, progress_callback=None, max_workers=4):
    # Two-pass: first by size, then by checksum (parallel)
    potential_dupes = find_potential_duplicates(files)
    checksums = compute_checksums(potential_dupes, progress_callback, max_workers)
    checksum_map = {}
    for file, checksum in checksums.items():
        checksum_map.setdefault(checksum, []).append(file)
    return {k: v for k, v in checksum_map.items() if len(v) > 1}

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
    st.title("Duplicate Media Finder")
    st.write("Scan drives or folders for duplicate media files and annotate a listing for external review or action.")

    # Load settings
    settings = load_settings()
    # Sidebar layout improvements
    with st.sidebar:
        st.header("1. Discovery Mode")
        # Make 'Folders' the first option and default
        mode = st.radio("Choose how to scan:", ["Folders", "Drives"], index=0)
        st.markdown("---")
        st.header("2. Scan Targets")
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
            selected_folders = [f.strip() for f in selected_folders if f.strip()]
        st.markdown("---")
        st.header("3. Filetype Options")
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
        st.header("4. Skip Folders")
        if 'skip_folders' in settings:
            default_skip_folders = '\n'.join(settings['skip_folders'])
        else:
            default_skip_folders = '\n'.join(DEFAULT_SKIP_FOLDERS)
        skip_folders_input = st.text_area(
            "Skip these folders (one per line)",
            value=default_skip_folders
        )
        skip_folders = [f.strip() for f in skip_folders_input.splitlines() if f.strip()]
        st.markdown("---")
        st.header("5. Actions")
        inventory_clicked = st.button("Inventory Media Files")
    # Save settings if changed
    if set(media_extensions) != set(settings.get('file_types', [])) or skip_folders != settings.get('skip_folders', []):
        settings['file_types'] = list(media_extensions)
        settings['skip_folders'] = skip_folders
        save_settings(settings)

    # Inventory
    if inventory_clicked:
        # Clear prior results from session state and show a placeholder while scanning
        st.session_state['media_files'] = []
        st.session_state['duplicates'] = {}
        st.session_state['annotations'] = {}
        st.session_state['scanning'] = True
        st.info("Scanning in progress. Results will appear when complete.")
        if mode == "Drives" and not selected_drives:
            st.warning("Please select at least one drive.")
        elif mode == "Folders" and not selected_folders:
            st.warning("Please enter at least one folder path.")
        else:
            with st.spinner("Scanning for media files..."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                def progress_callback(done, total):
                    progress_bar.progress(min(done / total, 1.0))
                    status_text.text(f"Scanning folder {done} of {total}")
                scan_targets = selected_drives if mode == "Drives" else selected_folders
                files = find_media_files(scan_targets, media_extensions, progress_callback, skip_folders)
                st.session_state['media_files'] = files
                st.session_state['scanning'] = False
                progress_bar.empty()
                status_text.text(f"Found {len(files)} media files.")
                st.success(f"Found {len(files)} media files.")

    # Find duplicates
    if 'media_files' in st.session_state:
        if st.button("Find Duplicates"):
            with st.spinner("Calculating checksums and finding duplicates..."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                def progress_callback(done, total):
                    progress_bar.progress(min(done / total, 1.0))
                    status_text.text(f"Checksummed {done} of {total} files")
                dupes = group_by_checksum_parallel(st.session_state['media_files'], progress_callback, max_workers=8)
                st.session_state['duplicates'] = dupes
                st.session_state['annotations'] = {}
                progress_bar.empty()
                status_text.text(f"Found {sum(len(v) for v in dupes.values())} duplicate files.")
                st.success(f"Found {sum(len(v) for v in dupes.values())} duplicate files.")

    # Only show results if there are any and not scanning
    if st.session_state.get('media_files') and len(st.session_state['media_files']) > 0 and not st.session_state.get('scanning', False):
        # Annotate and export with table view
        if 'duplicates' in st.session_state:
            st.header("Duplicate Groups Table View")
            # Build table data
            table_rows = []
            for checksum, files in st.session_state['duplicates'].items():
                for file in files:
                    size = os.path.getsize(file) if os.path.exists(file) else 0
                    ext = os.path.splitext(file)[1].lower()
                    annotation = st.session_state['annotations'].get(file, "None")
                    table_rows.append({
                        "file_name": os.path.basename(file),
                        "full_path": file,
                        "size": size,
                        "file_type": ext,
                        "checksum": checksum,
                        "disposition": annotation
                    })
            df = pd.DataFrame(table_rows)
            # Add disposition selectbox per row
            if not df.empty:
                st.set_page_config(layout="wide")
                def shorten_path(path, max_len=60):
                    if len(path) <= max_len:
                        return path
                    else:
                        return '...' + path[-max_len:]
                df['short_path'] = df['full_path'].apply(lambda p: shorten_path(p, 60))

                # Add column for duplicate file paths
                def get_other_duplicates(row, df):
                    same_checksum = df[(df['checksum'] == row['checksum']) & (df['full_path'] != row['full_path'])]
                    return '; '.join(same_checksum['full_path'].tolist())
                df['duplicate_of'] = df.apply(lambda row: get_other_duplicates(row, df), axis=1)

                filter_disp = st.selectbox("Filter by disposition", ["All"] + ["None", "Keep", "Delete", "Move", "Review"])
                filtered_df = df if filter_disp == "All" else df[df['disposition'] == filter_disp]
                # Use data_editor for interactive row selection (without on_select, which is not supported)
                # Remove 'Selected' column and use selectbox for single-row selection
                st.data_editor(
                    df[["file_name", "short_path", "size", "file_type", "checksum", "disposition", "duplicate_of"]],
                    use_container_width=True,
                    hide_index=True,
                    key="dupes_editor",
                    num_rows="dynamic",
                    disabled=["file_name", "short_path", "size", "file_type", "checksum", "disposition", "duplicate_of"]
                )
                # Use a selectbox for single-row selection
                selected_row_idx = st.selectbox(
                    "Select a file to annotate:",
                    options=list(df.index),
                    format_func=lambda i: f"{df.at[i, 'file_name']} ({df.at[i, 'short_path']})",
                    index=st.session_state.get('selected_row_idx', 0) if st.session_state.get('selected_row_idx', 0) < len(df) else 0
                )
                st.session_state['selected_row_idx'] = selected_row_idx
                selected_row = df.loc[selected_row_idx]
                key = f"annotate_{selected_row['full_path']}"
                col1, col2, col3 = st.columns([1,1,2])
                with col1:
                    if st.button(f"Open {selected_row['file_name']}"):
                        try:
                            os.startfile(selected_row['full_path'])
                        except Exception as e:
                            st.error(f"Could not open file: {e}")
                with col2:
                    if st.button("Open Folder"):
                        try:
                            folder = os.path.dirname(selected_row['full_path'])
                            os.startfile(folder)
                        except Exception as e:
                            st.error(f"Could not open folder: {e}")
                with col3:
                    # Add 'Ignore Folder' disposition option
                    disposition_options = ["None", "Keep", "Delete", "Move", "Review", "Ignore Folder"]
                    new_disp = st.selectbox(
                        f"Disposition for {selected_row['file_name']}",
                        disposition_options,
                        key=key,
                        index=disposition_options.index(selected_row['disposition']) if selected_row['disposition'] in disposition_options else 0
                    )
                    df.loc[df['full_path'] == selected_row['full_path'], 'disposition'] = new_disp
                    st.session_state['annotations'][selected_row['full_path']] = new_disp

                # If 'Ignore Folder' is selected, update skip list, config, and filter table
                if new_disp == "Ignore Folder":
                    folder = os.path.dirname(selected_row['full_path'])
                    if folder not in skip_folders:
                        skip_folders.append(folder)
                        settings['skip_folders'] = skip_folders
                        save_settings(settings)
                    # Filter out files in ignored folder
                    df = df[df['full_path'].apply(lambda p: os.path.dirname(p) not in skip_folders)]
                    st.warning("Folder added to skip list. Please click 'Inventory Media Files' to refresh the table.")
                    return
            else:
                st.info("No duplicates found.")
            # Export
            if st.button("Export Annotations to CSV"):
                export_df = df.copy()
                export_df.to_csv("duplicate_media_annotations.csv", index=False)
                st.download_button(
                    label="Download CSV",
                    data=export_df.to_csv(index=False),
                    file_name="duplicate_media_annotations.csv",
                    mime="text/csv"
                )
    elif st.session_state.get('scanning', False):
        with st.expander("Previous results (hidden during scan)", expanded=False):
            st.write("Previous results are hidden while scanning is in progress.")

if __name__ == "__main__":
    main()
