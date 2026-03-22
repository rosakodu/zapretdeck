import os
import subprocess
import tempfile
import logging
import shutil
from typing import Optional

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from github_release_updates import DEFAULT_REPO, Channel, check_for_updates_sync

logger = logging.getLogger(__name__)


class UpdateChecker(QThread):
    """Фоновая проверка обновлений через GitHub Releases (см. github_release_updates)."""

    update_available = pyqtSignal(str, str)  # tag_name, zipball_url

    def __init__(
        self,
        current_version: str,
        channel: Channel,
        repo: Optional[str] = None,
    ):
        super().__init__()
        self.current_version = current_version
        self.channel = channel
        self.repo = repo

    def run(self) -> None:
        try:
            info, err = check_for_updates_sync(
                self.current_version,
                self.channel,
                repo=self.repo or DEFAULT_REPO,
                timeout=15.0,
            )
            if err:
                logger.warning("Проверка обновлений не выполнена: %s", err)
                return
            if info:
                logger.info(
                    "Доступно обновление: tag=%s semver=%s (канал=%s)",
                    info.tag_name,
                    info.semver_text,
                    self.channel,
                )
                self.update_available.emit(info.tag_name, info.zipball_url)
        except Exception as e:
            logger.error("Проверка обновлений: неожиданная ошибка: %s", e)


class UpdaterWorker(QThread):
    """Скачивание zipball и запуск install.sh в терминале (после подтверждения в GUI)."""

    update_finished = pyqtSignal(bool, str)

    def __init__(self, download_url: str):
        super().__init__()
        self.download_url = download_url

    def run(self) -> None:
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp()
            zip_path = os.path.join(temp_dir, "update.zip")

            response = requests.get(
                self.download_url,
                stream=True,
                timeout=60,
                headers={"User-Agent": "ZapretDeck-Updater"},
            )
            response.raise_for_status()

            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            subprocess.run(["unzip", "-q", zip_path, "-d", extract_dir], check=True)

            extracted_items = os.listdir(extract_dir)
            if not extracted_items:
                raise RuntimeError("Пустой zip-архив")

            inner_dir = os.path.join(extract_dir, extracted_items[0])
            install_script = os.path.join(inner_dir, "install.sh")
            if os.path.exists(install_script):
                terminals = [
                    "konsole",
                    "gnome-terminal",
                    "xfce4-terminal",
                    "alacritty",
                    "kitty",
                    "xterm",
                    "lxterminal",
                ]
                term_cmd = None
                for t in terminals:
                    if subprocess.run(["which", t], capture_output=True).returncode == 0:
                        term_cmd = t
                        break
                if term_cmd:
                    cmd_str = (
                        f"cd '{inner_dir}' && bash ./install.sh; "
                        "echo 'Press Enter to close...'; read"
                    )
                    if term_cmd == "gnome-terminal":
                        subprocess.Popen([term_cmd, "--", "bash", "-c", cmd_str])
                    else:
                        subprocess.Popen([term_cmd, "-e", "bash", "-c", cmd_str])
                    self.update_finished.emit(True, "Update started in terminal.")
                else:
                    self.update_finished.emit(
                        False,
                        "No terminal emulator found to run the installer.",
                    )
            else:
                self.update_finished.emit(False, "install.sh not found in the update package.")

        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            self.update_finished.emit(False, f"Download failed: HTTP {code}")
        except Exception as e:
            self.update_finished.emit(False, str(e))
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
