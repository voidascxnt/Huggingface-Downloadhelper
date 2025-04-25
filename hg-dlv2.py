#!/usr/bin/env python3
import os
import sys
import requests
import re
import time
import threading
from huggingface_hub import HfApi
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QLabel, QLineEdit, 
                            QFileDialog, QProgressBar, QSlider, QListWidget, 
                            QListWidgetItem, QMessageBox, QMenu, QScrollArea)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer

# Shared state object for communication between threads
class DownloadState(QObject):
    progress_update = pyqtSignal(str, int, float, float)
    download_complete = pyqtSignal(str, bool)
    file_list_ready = pyqtSignal(list)
    status_update = pyqtSignal(str)
    speed_changed = pyqtSignal(int)
    download_started = pyqtSignal(str)  # New signal for when a download starts
    
    def __init__(self):
        super().__init__()
        self.current_rate_limit = 500  # Initial rate limit in KB/s
        self.should_pause = False
        self.should_cancel = False
        self.active_downloads = {}  # Track active downloads
        self.active_downloads_lock = threading.Lock()
        
    def on_speed_changed(self, new_value):
        self.current_rate_limit = new_value
        
    def register_download(self, filename):
        with self.active_downloads_lock:
            self.active_downloads[filename] = {
                'start_time': time.time(),
                'downloaded': 0
            }
            
    def update_download_progress(self, filename, bytes_downloaded):
        with self.active_downloads_lock:
            if filename in self.active_downloads:
                self.active_downloads[filename]['downloaded'] = bytes_downloaded
                
    def get_current_rate_per_download(self):
        with self.active_downloads_lock:
            active_count = len(self.active_downloads)
            if active_count > 0:
                # Divide bandwidth among active downloads, with a minimum per download
                return max(50, self.current_rate_limit / active_count)
            return self.current_rate_limit
            
    def unregister_download(self, filename):
        with self.active_downloads_lock:
            if filename in self.active_downloads:
                del self.active_downloads[filename]
        
download_state = DownloadState()
speed_mutex = threading.Lock() # Mutex for thread-safe access to speed limit

def get_model_files(repo_id, token=None):
    try:
        api = HfApi(token=token)
        files = api.list_repo_files(repo_id)
        return files
    except Exception as e:
        download_state.status_update.emit(f"Error retrieving files: {str(e)}")
        return []

def sort_model_files(files):
    # Identifiziere Shard-Dateien (model-00001-of-00005.safetensors etc.)
    shard_pattern = r'.*-\d+-of-\d+\..*'
    
    shard_files = [f for f in files if re.match(shard_pattern, os.path.basename(f))]
    other_files = [f for f in files if f not in shard_files]
    
    # Sortiere Shard-Dateien nach ihrer Nummer
    def get_shard_number(filename):
        match = re.search(r'-(\d+)-of-', os.path.basename(filename))
        if match:
            return int(match.group(1))
        return 0
    
    shard_files.sort(key=get_shard_number)
    
    # Konfigurationsdateien zuerst, dann Shards, dann Rest
    config_files = [f for f in other_files if f.endswith(('.json', '.txt', '.md'))]
    remaining_files = [f for f in other_files if f not in config_files]
    
    return config_files + shard_files + remaining_files

def download_file_with_rate_limit(repo_id, filename, output_dir, token=None):
    output_path = os.path.join(output_dir, filename)
    
    # Erstelle Verzeichnisstruktur
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    
    # URL zur Datei
    file_url = f"https://huggingface.co/{repo_id}/resolve/main/{filename}"
    if token:
        file_url += f"?token={token}"
    
    download_state.status_update.emit(f"Downloading {filename}...")
    
    # Register this download and notify UI
    download_state.register_download(filename)
    download_state.download_started.emit(filename)
    
    # Starte Download mit manuellem Chunk-Downloading für Ratenbegrenzung
    try:
        response = requests.get(file_url, stream=True)
        response.raise_for_status()
    except Exception as e:
        download_state.status_update.emit(f"Error starting download: {str(e)}")
        download_state.unregister_download(filename)
        download_state.download_complete.emit(filename, False)
        return False
    
    total_size = int(response.headers.get('content-length', 0))
    chunk_size = 8192  # 8KB chunks
    downloaded = 0
    
    temp_path = output_path + ".partial"
    with open(temp_path, 'wb') as f:
        start_time = time.time()
        last_update_time = start_time
        update_interval = 0.5  # Update UI every 0.5 seconds
        
        try:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if download_state.should_cancel:
                    download_state.status_update.emit("Download abgebrochen.")
                    download_state.unregister_download(filename)
                    download_state.download_complete.emit(filename, False)
                    return False
                
                # Pause if needed
                while download_state.should_pause and not download_state.should_cancel:
                    time.sleep(0.1)
                    
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    download_state.update_download_progress(filename, downloaded)
                    
                    # Berechne die Dauer und passe die Geschwindigkeit an
                    elapsed = time.time() - start_time
                    current_limit = download_state.get_current_rate_per_download()
                    
                    if elapsed > 0:
                        rate = downloaded / elapsed / 1024  # KB/s
                        
                        # Wenn wir zu schnell sind, warten wir ein bisschen
                        if rate > current_limit:
                            time_to_sleep = (downloaded / (current_limit * 1024)) - elapsed
                            if time_to_sleep > 0:
                                time.sleep(time_to_sleep)
                    
                    # Update progress UI at regular intervals
                    current_time = time.time()
                    if current_time - last_update_time >= update_interval:
                        last_update_time = current_time
                        elapsed = current_time - start_time
                        rate = downloaded / elapsed / 1024 if elapsed > 0 else 0
                        percent = int(100 * downloaded / total_size) if total_size > 0 else 0
                        download_state.progress_update.emit(filename, percent, downloaded/(1024*1024), total_size/(1024*1024))
        
        except Exception as e:
            download_state.status_update.emit(f"Error during download: {str(e)}")
            download_state.unregister_download(filename)
            download_state.download_complete.emit(filename, False)
            return False
    
    # Unregister download before finalizing
    download_state.unregister_download(filename)
    
    # Rename the partial file to the final filename
    try:
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(temp_path, output_path)
    except Exception as e:
        download_state.status_update.emit(f"Error renaming file: {str(e)}")
        download_state.download_complete.emit(filename, False)
        return False
        
    download_state.status_update.emit(f"✓ Successfully downloaded: {filename}")
    download_state.download_complete.emit(filename, True)
    return True

def download_single_file_thread(repo_id, filename, output_dir, token=None):
    success = download_file_with_rate_limit(repo_id, filename, output_dir, token)
    return success

def download_thread_func(repo_id, output_dir, file_list, token=None):
    download_state.status_update.emit(f"Starting downloads for {repo_id}...")
    
    for filename in file_list:
        if download_state.should_cancel:
            download_state.status_update.emit("All downloads canceled.")
            break
            
        success = download_file_with_rate_limit(repo_id, filename, output_dir, token)
        if not success and not download_state.should_cancel:
            download_state.status_update.emit(f"Download of {filename} failed. Continuing with next file...")
    
    download_state.status_update.emit("All downloads completed" if not download_state.should_cancel else "Downloads canceled")

def get_files_thread_func(repo_id, token=None):
    download_state.status_update.emit(f"Retrieving file list for {repo_id}...")
    files = get_model_files(repo_id, token)
    if files:
        sorted_files = sort_model_files(files)
        download_state.file_list_ready.emit(sorted_files)
        download_state.status_update.emit(f"Found: {len(sorted_files)} files to download")
    else:
        download_state.status_update.emit("No files found or error retrieving file list.")
        download_state.file_list_ready.emit([])

class ProgressBarWidget(QWidget):
    def __init__(self, filename, parent=None):
        super().__init__(parent)
        self.filename = filename
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # File label
        self.label = QLabel(f"Downloading: {filename}")
        layout.addWidget(self.label)
        
        # Progress info layout
        info_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        info_layout.addWidget(self.progress_bar, 1)  # Give progress bar stretch priority
        self.details_label = QLabel("0 MB / 0 MB (0%)")
        info_layout.addWidget(self.details_label)
        layout.addLayout(info_layout)
        
        self.setLayout(layout)
    
    def update_progress(self, percent, downloaded_mb, total_mb):
        self.progress_bar.setValue(percent)
        self.details_label.setText(f"{downloaded_mb:.1f} MB / {total_mb:.1f} MB ({percent}%)")
    
    def mark_complete(self, success):
        if success:
            self.label.setText(f"✓ Completed: {self.filename}")
            self.progress_bar.setValue(100)
        else:
            self.label.setText(f"✗ Failed: {self.filename}")

class HuggingFaceDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hugging Face Model Downloader")
        self.setGeometry(100, 100, 800, 600)
        
        self.file_list = []
        self.download_thread = None
        self.current_downloading_file = None
        self.progress_bars = {}  # Dictionary to store progress bar widgets by filename
        
        self.init_ui()
        self.connect_signals()
        
    def init_ui(self):
        main_widget = QWidget()
        self.main_layout = QVBoxLayout()
        
        # Input section
        input_layout = QVBoxLayout()
        
        repo_layout = QHBoxLayout()
        repo_layout.addWidget(QLabel("Repository ID:"))
        self.repo_id_input = QLineEdit()
        self.repo_id_input.setPlaceholderText("e.g., nbeerbower/Mistral-Nemo-Gutenberg-Doppel-12B-v2")
        repo_layout.addWidget(self.repo_id_input)
        self.load_files_btn = QPushButton("Load Files")
        repo_layout.addWidget(self.load_files_btn)
        
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output Directory:"))
        self.output_dir_input = QLineEdit()
        self.output_dir_input.setPlaceholderText("Path to save files")
        output_layout.addWidget(self.output_dir_input)
        self.browse_btn = QPushButton("Browse...")
        output_layout.addWidget(self.browse_btn)
        
        token_layout = QHBoxLayout()
        token_layout.addWidget(QLabel("API Token (optional):"))
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("For private repositories")
        token_layout.addWidget(self.token_input)
        
        input_layout.addLayout(repo_layout)
        input_layout.addLayout(output_layout)
        input_layout.addLayout(token_layout)
        
        self.main_layout.addLayout(input_layout)
        
        # File list
        list_layout = QVBoxLayout()
        list_layout.addWidget(QLabel("Files to Download:"))
        self.file_list_widget = QListWidget()
        list_layout.addWidget(self.file_list_widget)
        
        self.main_layout.addLayout(list_layout)
        
        # Speed control
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Download Speed:"))
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(50)
        self.speed_slider.setMaximum(10000)
        self.speed_slider.setValue(500)
        self.speed_slider.setTickInterval(500)
        self.speed_slider.setTickPosition(QSlider.TicksBelow)
        speed_layout.addWidget(self.speed_slider)
        self.speed_label = QLabel("500 KB/s")
        speed_layout.addWidget(self.speed_label)
        
        # Create a scroll area for progress bars
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(150)
        
        # Container widget for progress bars
        self.progress_container = QWidget()
        self.progress_layout = QVBoxLayout(self.progress_container)
        self.progress_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.progress_container)
        
        # Status section
        self.status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_layout.addWidget(self.status_label)
        
        self.start_btn = QPushButton("Start")
        self.start_btn.setEnabled(False)
        self.status_layout.addWidget(self.start_btn)
        
        self.pause_resume_btn = QPushButton("Pause")
        self.pause_resume_btn.setEnabled(False)
        self.status_layout.addWidget(self.pause_resume_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.status_layout.addWidget(self.cancel_btn)
        
        # Add everything to main layout
        self.main_layout.addWidget(self.scroll_area)
        self.main_layout.addLayout(self.status_layout)
        
        main_widget.setLayout(self.main_layout)
        self.setCentralWidget(main_widget)
    
    def connect_signals(self):
        self.load_files_btn.clicked.connect(self.load_files)
        self.browse_btn.clicked.connect(self.browse_output_dir)
        self.start_btn.clicked.connect(self.start_download)
        self.pause_resume_btn.clicked.connect(self.toggle_pause_resume)
        self.cancel_btn.clicked.connect(self.cancel_download)
        self.speed_slider.valueChanged.connect(self.update_speed_limit)
        
        # Connect download state signals
        download_state.progress_update.connect(self.update_progress)
        download_state.download_complete.connect(self.on_file_download_complete)
        download_state.file_list_ready.connect(self.on_file_list_ready)
        download_state.status_update.connect(self.update_status)
        download_state.speed_changed.connect(download_state.on_speed_changed)
        download_state.download_started.connect(self.on_download_started)
    
    def load_files(self):
        repo_id = self.repo_id_input.text().strip()
        if not repo_id:
            QMessageBox.warning(self, "Error", "Please enter a Repository ID")
            return
            
        token = self.token_input.text().strip() or None
        
        # Reset UI for new file list
        self.file_list_widget.clear()
        self.file_list = []
        self.start_btn.setEnabled(False)
        
        # Start thread to fetch files
        threading.Thread(target=get_files_thread_func, args=(repo_id, token), daemon=True).start()
    
    def browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.output_dir_input.setText(dir_path)

    def update_speed_limit(self, value):
        self.speed_label.setText(f"{value} KB/s")
        download_state.speed_changed.emit(value)
    
    def start_download(self):
        if self.download_thread and self.download_thread.is_alive():
            return
            
        repo_id = self.repo_id_input.text().strip()
        output_dir = self.output_dir_input.text().strip()
        token = self.token_input.text().strip() or None
        
        if not repo_id or not output_dir:
            QMessageBox.warning(self, "Error", "Please enter Repository ID and Output Directory")
            return
            
        if not os.path.isdir(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Cannot create output directory: {str(e)}")
                return
        
        # Get only enabled files
        enabled_files = []
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            if item.data(Qt.UserRole + 1):  # If enabled
                filename = item.text().split(" - ")[0]  # Get clean filename
                enabled_files.append(filename)
        
        if not enabled_files:
            QMessageBox.warning(self, "Warning", "No files are enabled for download")
            return
        
        # Reset download state
        download_state.should_pause = False
        download_state.should_cancel = False
        
        # Update UI
        self.progress_container.setVisible(True)
        self.pause_resume_btn.setText("Pause")
        self.pause_resume_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.start_btn.setEnabled(False)
        self.load_files_btn.setEnabled(False)
        
        # Start download thread with enabled files only
        self.download_thread = threading.Thread(
            target=download_thread_func, 
            args=(repo_id, output_dir, enabled_files, token), 
            daemon=True
        )
        self.download_thread.start()
    
    def toggle_pause_resume(self):
        if download_state.should_pause:
            download_state.should_pause = False
            self.pause_resume_btn.setText("Pause")
            self.update_status("Download resumed")
        else:
            download_state.should_pause = True
            self.pause_resume_btn.setText("Resume")
            self.update_status("Download paused")
    
    def cancel_download(self):
        download_state.should_cancel = True
        download_state.should_pause = False
        self.pause_resume_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.update_status("Cancelling downloads...")
    
    def on_file_list_ready(self, file_list):
        self.file_list = file_list
        self.file_list_widget.clear()
        
        for filename in file_list:
            item = QListWidgetItem(filename)
            item.setData(Qt.UserRole, "pending")  # Status: pending
            item.setData(Qt.UserRole + 1, True)   # Enabled for download: True
            self.file_list_widget.addItem(item)
        
        if file_list:
            self.start_btn.setEnabled(True)
            
            # Set up context menu for the file list
            self.file_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            self.file_list_widget.customContextMenuRequested.connect(self.show_context_menu)
    
    def update_progress(self, filename, percent, downloaded_mb, total_mb):
        # Update file list display
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            if item.text().startswith(filename):
                item.setText(f"{filename} - {percent}%")
                item.setData(Qt.UserRole, "downloading")
                self.current_downloading_file = filename
                break
        
        # Update progress bar if it exists
        if filename in self.progress_bars:
            self.progress_bars[filename].update_progress(percent, downloaded_mb, total_mb)
    
    def on_file_download_complete(self, filename, success):
        # Update the item in the list
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            if item.text().startswith(filename):
                if success:
                    item.setText(f"{filename} - ✓")
                    item.setData(Qt.UserRole, "completed")
                else:
                    item.setText(f"{filename} - ✗")
                    item.setData(Qt.UserRole, "failed")
                break
        
        # Update the progress bar
        if filename in self.progress_bars:
            self.progress_bars[filename].mark_complete(success)
            
            # Schedule removal of the progress bar after a delay
            QTimer.singleShot(3000, lambda: self.remove_progress_bar(filename))
        
        # Reset current file display if needed
        if self.current_downloading_file == filename:
            self.current_downloading_file = None
            
        # Check if the download thread is done
        if not self.download_thread or not self.download_thread.is_alive():
            self.start_btn.setEnabled(True)
            self.pause_resume_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
            self.load_files_btn.setEnabled(True)
    
    def remove_progress_bar(self, filename):
        if filename in self.progress_bars:
            # Remove the widget from layout and delete it
            progress_bar = self.progress_bars[filename]
            self.progress_layout.removeWidget(progress_bar)
            progress_bar.deleteLater()
            del self.progress_bars[filename]
            
            # Adjust window height if needed
            if len(self.progress_bars) < 3:
                self.resize(self.width(), 600)  # Reset to default height
    
    def update_status(self, message):
        self.status_label.setText(message)
    
    def show_context_menu(self, position):
        menu = QMenu()
        
        # Get the item under cursor
        item = self.file_list_widget.itemAt(position)
        if item:
            # Get clean filename (without status indicators)
            display_text = item.text()
            filename = display_text.split(" - ")[0]  # Strip status indicators
            status = item.data(Qt.UserRole)
            is_enabled = item.data(Qt.UserRole + 1)
            
            # Only allow "Download this file" for pending files
            if status == "pending":
                download_action = menu.addAction("Download this file")
                download_action.triggered.connect(lambda: self.download_single_file(filename))
                
                # Add toggle option for enabling/disabling
                if is_enabled:
                    disable_action = menu.addAction("Disable download")
                    disable_action.triggered.connect(lambda: self.toggle_file_download(item, False))
                else:
                    enable_action = menu.addAction("Enable download")
                    enable_action.triggered.connect(lambda: self.toggle_file_download(item, True))
            
        menu.exec_(self.file_list_widget.mapToGlobal(position))
    
    def toggle_file_download(self, item, enable):
        display_text = item.text()
        filename = display_text.split(" - ")[0]  # Strip status indicators
        
        # Update the item's enabled state
        item.setData(Qt.UserRole + 1, enable)
        
        # Update the item's appearance
        if enable:
            item.setText(filename)
            item.setForeground(self.palette().text()) # Use default text color for enabled
        else:
            item.setText(f"{filename} [DISABLED]") # Add indicator to text
            item.setForeground(Qt.gray) # Use gray color for disabled
            
        # Count enabled files and update status
        enabled_count = 0
        for i in range(self.file_list_widget.count()):
            if self.file_list_widget.item(i).data(Qt.UserRole + 1):
                enabled_count += 1
                
        self.update_status(f"{enabled_count} of {self.file_list_widget.count()} files enabled for download")

    def download_single_file(self, filename):
        # Validate inputs
        repo_id = self.repo_id_input.text().strip()
        output_dir = self.output_dir_input.text().strip()
        token = self.token_input.text().strip() or None
        if not repo_id or not output_dir:
            QMessageBox.warning(self, "Error", "Please enter Repository ID and Output Directory")
            return
        if not os.path.isdir(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Cannot create output directory: {str(e)}")
                return
        # Mark this file as downloading in the UI
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            # Get clean filename (without status indicators)
            display_text = item.text()
            current_filename = display_text.split(" - ")[0]
            if current_filename == filename:
                item.setText(f"{filename} - 0%")
                item.setData(Qt.UserRole, "downloading")
                break
        # Emit signal to show we're starting a download
        download_state.download_started.emit(filename)
        # Start a thread for this file download
        thread = threading.Thread(
            target=download_single_file_thread,
            args=(repo_id, filename, output_dir, token),
            daemon=True
        )
        thread.start()
def main():
    app = QApplication(sys.argv)
    window = HuggingFaceDownloaderGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()_ == "__main__":
    main()
