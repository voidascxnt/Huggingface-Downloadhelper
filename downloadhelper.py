import os
import re
import requests
import threading
from huggingface_hub import hf_hub_download, HfApi
from tqdm import tqdm

class DownloadManager:
    def __init__(self):
        self.active_downloads = set()
        self._lock = threading.Lock()
    
    def is_active(self, model_id):
        with self._lock:
            return model_id in self.active_downloads
    
    def add_download(self, model_id):
        with self._lock:
            if model_id in self.active_downloads:
                return False
            self.active_downloads.add(model_id)
            return True
    
    def remove_download(self, model_id):
        with self._lock:
            if model_id in self.active_downloads:
                self.active_downloads.remove(model_id)

# Global download manager instance
download_manager = DownloadManager()

class HuggingfaceDownloader:
    def __init__(self, save_path="./models", use_auth=True, token=None, no_auto_next=False):
        self.save_path = save_path
        self.use_auth = use_auth
        self.token = token or os.environ.get("HF_TOKEN")
        self.no_auto_next = no_auto_next
        
        # Create directory if it doesn't exist
        os.makedirs(save_path, exist_ok=True)
    
    def download(self, model_id, revision=None, filenames=None, resume=True):
        # Check if this model is already being downloaded
        if not download_manager.add_download(model_id):
            print(f"Model {model_id} is already being downloaded. Skipping.")
            return False
        
        try:
            print(f"Starting download of {model_id}")
            
            # Get model files
            api = HfApi(token=self.token if self.use_auth else None)
            files = api.list_repo_files(model_id, revision=revision)
            
            if filenames:
                files = [f for f in files if f in filenames]
            
            # Download each file
            for file in files:
                try:
                    hf_hub_download(
                        repo_id=model_id,
                        filename=file,
                        revision=revision,
                        token=self.token if self.use_auth else None,
                        local_dir=self.save_path,
                        resume_download=resume
                    )
                    print(f"Successfully downloaded {file} from {model_id}")
                except Exception as e:
                    print(f"Error downloading {file}: {e}")
            
            # Check if we should queue the next part
            self.queue_next_part(model_id)
            
            return True
        finally:
            # Always remove from active downloads when done
            download_manager.remove_download(model_id)
    
    def queue_next_part(self, current_model_id):
        """Queue the next part if auto-queuing is enabled"""
        if self.no_auto_next:
            return
            
        # Parse the current model ID to find the part number
        match = re.search(r'part(\d+)', current_model_id)
        if not match:
            return
            
        current_part = int(match.group(1))
        next_part = current_part + 1
        base_model_id = current_model_id.replace(f"part{current_part}", f"part{next_part}")
        
        # Don't queue if already downloading
        if download_manager.is_active(base_model_id):
            print(f"Next part {base_model_id} is already downloading. Not queuing.")
            return
            
        print(f"Queuing next part: {base_model_id}")
        self.download(base_model_id)

# Command-line interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Download models from Huggingface Hub")
    parser.add_argument("model_id", help="Huggingface model ID to download")
    parser.add_argument("--save-path", default="./models", help="Directory to save the model")
    parser.add_argument("--no-auth", action="store_true", help="Disable authentication")
    parser.add_argument("--token", help="Huggingface token")
    parser.add_argument("--revision", help="Branch or commit to download from")
    parser.add_argument("--files", help="Comma-separated list of files to download")
    parser.add_argument("--no-resume", action="store_true", help="Don't resume interrupted downloads")
    parser.add_argument("--no-auto-next", action="store_true", help="Don't automatically queue next part")
    
    args = parser.parse_args()
    
    # Convert comma-separated files to list
    filenames = args.files.split(",") if args.files else None
    
    # Create downloader
    downloader = HuggingfaceDownloader(
        save_path=args.save_path,
        use_auth=not args.no_auth,
        token=args.token,
        no_auto_next=args.no_auto_next
    )
    
    # Start download
    downloader.download(
        model_id=args.model_id,
        revision=args.revision,
        filenames=filenames,
        resume=not args.no_resume
    )