import os
import subprocess
import tempfile
import requests
import logging
import shutil
from packaging import version
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

class UpdateChecker(QThread):
    update_available = pyqtSignal(str, str) # version, download_url

    def __init__(self, current_version: str, check_prerelease: bool = False):
        super().__init__()
        self.current_version = current_version
        self.check_prerelease = check_prerelease

    def run(self):
        try:
            url = "https://api.github.com/repos/rosakodu/zapretdeck/releases"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                releases = response.json()
                for release in releases:
                    is_prerelease = release.get("prerelease", False)
                    if self.check_prerelease == is_prerelease:
                        tag_name = release.get("tag_name", "").lstrip("v.")
                        # Always pull from master branch zipball as requested by user
                        download_url = "https://github.com/rosakodu/zapretdeck/archive/refs/heads/master.zip"
                        if self.check_prerelease:
                             download_url = release.get("zipball_url") # For DEVEL keep release zip for now
                             
                        if self.is_newer(tag_name, self.current_version):
                            self.update_available.emit(tag_name, download_url)
                        break
        except Exception as e:
            logger.error(f"Failed to check for updates: {e}")

    def is_newer(self, remote_ver, local_ver):
        try:
            # Clean version strings
            r_clean = remote_ver.replace("v", "").replace("DEVEL", "").strip()
            l_clean = local_ver.replace("v", "").replace("DEVEL", "").strip()
            
            # Use packaging.version for robust comparison
            return version.parse(r_clean) > version.parse(l_clean)
        except Exception as e:
            logger.error(f"Version comparison failed: {e}")
            return False

class UpdaterWorker(QThread):
    update_finished = pyqtSignal(bool, str)
    
    def __init__(self, download_url):
        super().__init__()
        self.download_url = download_url
        
    def run(self):
        try:
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, "update.zip")
            
            response = requests.get(self.download_url, stream=True, timeout=30)
            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            subprocess.run(["unzip", "-q", zip_path, "-d", extract_dir], check=True)
            
            extracted_items = os.listdir(extract_dir)
            if not extracted_items:
                raise Exception("Empty zip archive")
            inner_dir = os.path.join(extract_dir, extracted_items[0])
            
            install_script = os.path.join(inner_dir, "install.sh")
            if os.path.exists(install_script):
                terminals = ["konsole", "gnome-terminal", "xfce4-terminal", "alacritty", "kitty", "xterm", "lxterminal"]
                term_cmd = None
                for t in terminals:
                    if subprocess.run(["which", t], capture_output=True).returncode == 0:
                        term_cmd = t
                        break
                if term_cmd:
                    subprocess.Popen([term_cmd, "-e", f"bash '{install_script}'"])
                    self.update_finished.emit(True, "Update started in terminal.")
                else:
                    self.update_finished.emit(False, "No terminal emulator found to run the installer.")
            else:
                self.update_finished.emit(False, "install.sh not found in the update package.")
            
        except Exception as e:
            self.update_finished.emit(False, str(e))
