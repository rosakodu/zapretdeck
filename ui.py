#!/usr/bin/env python3
"""
ZapretDeck UI Module

Handles the graphical user interface.
"""
import os
import subprocess
import sys
import threading
import webbrowser
import logging
from typing import Optional
from packaging import version
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFrame, QMessageBox,
    QInputDialog, QLineEdit, QGridLayout, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QCursor

from utils import (
    BASE_DIR, CUSTOM_STRATEGIES_DIR, LATEST_STRATEGIES_DIR,
    CONF_FILE, MAIN_SCRIPT, STOP_SCRIPT, RENAME_SCRIPT, SERVICE_SCRIPT,
    ICON_PATH, HIDDEN_STRATEGIES, ConfigManager,
    check_dependencies, load_strategies, is_service_running
)
from monitor import StatusChecker

logger = logging.getLogger(__name__)

CURRENT_VERSION = "0.1.7"


class ZapretGUI(QMainWindow):
    """Main GUI window for ZapretDeck."""
    
    status_requested = pyqtSignal(str, str)
    auto_discovery_done = pyqtSignal(str)
    set_button_busy = pyqtSignal(bool)
    
    def __init__(self, translator=None):
        """
        Initialize the GUI.
        
        Args:
            translator: QTranslator instance for localization
        """
        super().__init__()
        self.translator = translator
        
        self.setWindowTitle(self._tr("ZapretDeck"))
        self.setMinimumSize(800, 600)
        self.setObjectName("zapretdeck")
        self.setProperty("WM_CLASS", "zapretdeck")
        self.showMaximized()
        
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        
        self.sudo_password: Optional[str] = None
        self.config = ConfigManager()
        self.saved_strategy = self.config.load_strategy()
        self.game_filter_enabled = self.config.load_game_filter()
        self.is_running = False
        self.is_changing_service = False
        self.is_auto_discovering = False
        self.loading_dots = 0
        self.loading_timer = QTimer()
        self.loading_timer.timeout.connect(self.update_loading_animation)
        
        # Check dependencies
        deps_ok, missing = check_dependencies()
        if not deps_ok:
            missing_str = ", ".join(missing)
            self.show_msg(
                self._tr("Error"),
                self._tr("Missing dependencies! Install: {deps}").format(deps=missing_str)
            )
            sys.exit(1)
        
        self.init_ui()
        self.load_config()
        self.start_status_checker()
        QTimer.singleShot(1000, self.check_for_update)
        QTimer.singleShot(2000, self.sync_service_button_on_startup)
        
        self.status_requested.connect(self.show_status)
        self.auto_discovery_done.connect(self.on_auto_success)
        self.set_button_busy.connect(self.update_button_loading_state)
        
        self.show_status(self._tr("Ready to work!"), "#107C10")
    
    def _tr(self, text: str) -> str:
        """Translate text using QTranslator if available."""
        if self.translator:
            translated = QApplication.translate("ZapretGUI", text)
            return translated if translated else text
        return text
    
    def sync_service_button_on_startup(self) -> None:
        """Synchronize service button state on startup."""
        try:
            real_state = is_service_running()
            
            if self.service_btn.isChecked() != real_state:
                logger.info(
                    f"Service button sync: was {'enabled' if self.service_btn.isChecked() else 'disabled'} "
                    f"→ now {'enabled' if real_state else 'disabled'}"
                )
                self.service_btn.blockSignals(True)
                self.service_btn.setChecked(real_state)
                self.service_btn.blockSignals(False)
        except Exception as e:
            logger.error(f"Service button sync error: {e}")
    
    def update_button_loading_state(self, is_busy: bool) -> None:
        """Update button loading state during auto-discovery."""
        if is_busy:
            self.start_btn.setEnabled(False)
            self.start_btn.setText(self._tr("AUTO-DISCOVERY IN PROGRESS..."))
            self.start_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #FF8C00, stop:1 #FF4500);
                    color: white; 
                    font-weight: bold;
                    font-size: 20px;
                    border-radius: 12px;
                    border: none;
                    outline: none;
                }
            """)
        else:
            self.start_btn.setEnabled(True)
            self.start_btn.setStyleSheet("")
            self.apply_session_style(self.is_running)
    
    def on_auto_success(self, filename: str) -> None:
        """Handle successful auto-discovery."""
        self.set_button_busy.emit(False)
        
        # Сохраняем реальное имя файла в конфиг, но в UI оставляем "Автоподбор"
        self.config.save_strategy(filename)
        self.config.save()
        self.saved_strategy = filename
        
        # Запускаем основной скрипт – он сам прочитает стратегию из конфига
        self.run_main_script(self.sudo_password)

    def init_ui(self) -> None:
        """Initialize the user interface."""
        # Глобальное отключение рамки фокуса для всех кнопок и комбобоксов
        self.setStyleSheet("""
            QPushButton, QComboBox, QAbstractItemView {
                outline: none;
            }
            QPushButton:focus, QComboBox:focus {
                outline: none;
            }
        """)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        scroll.setWidget(container)
        self.setCentralWidget(scroll)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Top card with version and strategy
        top = QFrame()
        top.setProperty("class", "card")
        top.setMinimumHeight(120)
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(16, 16, 16, 16)
        
        self.version_label = QLabel(f"v{CURRENT_VERSION}")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #107C10;")
        top_layout.addWidget(self.version_label)
        
        combo_frame = self.create_labeled_combo(
            self._tr("Current bypass strategy:"), [], ""
        )
        self.strategy_combo = combo_frame.findChild(QComboBox)
        self.strategy_combo.setObjectName("strategy_combo")
        self.strategy_combo.currentTextChanged.connect(self.on_strategy_changed)
        top_layout.addWidget(combo_frame)
        
        layout.addWidget(top)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setMinimumHeight(1)
        layout.addWidget(sep)
        
        # Tiles panel
        tiles_frame = QFrame()
        tiles_frame.setObjectName("tiles_panel")
        tiles_layout = QHBoxLayout(tiles_frame)
        tiles_layout.setSpacing(4)
        tiles_layout.setContentsMargins(0, 0, 0, 0)
        
        tile_style = """
            QPushButton {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 14px;
                font-size: 13px;
                font-weight: bold;
                outline: none;
            }
            QPushButton:focus {
                outline: none;
            }
            QPushButton:checked {
                background-color: #107C10;
                color: white;
                border: 1px solid #107C10;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """
        
        self.service_btn = QPushButton(self._tr("Background Service"))
        self.service_btn.setCheckable(True)
        self.service_btn.setStyleSheet(tile_style)
        self.service_btn.clicked.connect(self.toggle_service_tile)
        
        self.game_filter_btn = QPushButton(self._tr("Game Filter"))
        self.game_filter_btn.setCheckable(True)
        self.game_filter_btn.setStyleSheet(tile_style)
        self.game_filter_btn.clicked.connect(self.toggle_game_filter_tile)
        
        tiles_layout.addWidget(self.service_btn, 1)
        tiles_layout.addWidget(self.game_filter_btn, 1)
        
        layout.addWidget(tiles_frame)
        
        # Start/Stop button
        self.start_btn = QPushButton(self._tr("START"))
        self.start_btn.setMinimumHeight(64)
        self.start_btn.clicked.connect(self.start_zapret)
        self.apply_session_style(False)
        layout.addWidget(self.start_btn)
        
        # Actions card
        actions_card = QFrame()
        actions_card.setProperty("class", "card")
        actions_layout = QGridLayout(actions_card)
        actions_layout.setContentsMargins(16, 16, 16, 16)
        actions_layout.setSpacing(12)
        
        actions = [
            (self._tr("VKontakte"), "https://vk.com/valvesteamdeck"),
            (self._tr("Telegram"), "https://t.me/deckru"),
            (self._tr("Support Author"), "https://vk.com/valvesteamdeck?w=donut_payment-199643211&levelId=1669"),
            ("MAX", "https://max.ru/valvesteamdeck"),
        ]
        for i, (text, url) in enumerate(actions):
            btn = QPushButton(text)
            btn.setObjectName("actionButton")
            btn.setMinimumHeight(44)
            btn.clicked.connect(lambda _, u=url: webbrowser.open(u))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Убираем фокус для декоративных кнопок
            actions_layout.addWidget(btn, i // 2, i % 2)
        
        layout.addWidget(actions_card)
        
        # Exit button
        exit_btn = QPushButton(self._tr("Exit"))
        exit_btn.setObjectName("exitButton")
        exit_btn.setMinimumHeight(56)
        exit_btn.clicked.connect(self.close)
        exit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Убираем фокус
        layout.addWidget(exit_btn)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px;")
        self.status_label.setMinimumHeight(30)
        layout.addWidget(self.status_label)
        
        # Update label
        self.update_label = QLabel("")
        self.update_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_label.setStyleSheet("color: #ff6b6b; font-weight: bold; font-size: 14px;")
        self.update_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.update_label.mousePressEvent = lambda e: webbrowser.open(
            "https://github.com/rosakodu/zapretdeck/releases/latest"
        )
        self.update_label.setMinimumHeight(30)
        layout.addWidget(self.update_label)
        
        layout.addStretch()
    
    def apply_session_style(self, running: bool) -> None:
        """Apply style to start/stop button based on session state."""
        if self.loading_timer.isActive() or getattr(self, 'is_auto_discovering', False):
            return
        
        text = self._tr("STOP") if running else self._tr("START")
        grad = (
            "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #E53935,stop:1 #B71C1C)"
            if running
            else "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4CAF50,stop:1 #2E7D32)"
        )
        self.start_btn.setText(text)
        self.start_btn.setStyleSheet(
            f"color:#fff; background:{grad}; border-radius:12px; font-weight:bold; font-size:20px; outline:none;"
        )
    
    def start_loading_animation(self, action: str) -> None:
        """Start loading animation on start/stop button."""
        self.loading_dots = 0
        base = self._tr("STARTING") if action == "start" else self._tr("STOPPING")
        self.start_btn.setText(f"{base}...")
        self.start_btn.setEnabled(False)
        self.loading_timer.start(500)
    
    def update_loading_animation(self) -> None:
        """Update loading animation dots."""
        self.loading_dots = (self.loading_dots + 1) % 4
        dots = "." * self.loading_dots
        current = self.start_btn.text().rstrip(".")
        self.start_btn.setText(f"{current}{dots}")
    
    def stop_loading_animation(self) -> None:
        """Stop loading animation."""
        self.loading_timer.stop()
        self.start_btn.setEnabled(True)
        self.apply_session_style(self.is_running)
    
    def start_zapret(self) -> None:
        """Handle start/stop button click."""
        if self.loading_timer.isActive():
            return
        
        try:
            service_running = is_service_running()
        except Exception:
            service_running = False
        
        password = self.ask_sudo_password()
        if not password:
            return
        
        current_strat = self.strategy_combo.currentText()
        
        if self.is_running or service_running:
            self.start_loading_animation("stop")
            QTimer.singleShot(100, lambda: self.stop_session(password, service_running))
            return
        
        if not current_strat:
            self.show_status(self._tr("Select a strategy!"), "#ff6b6b")
            return
        
        # Если выбран "Автоподбор"
        if current_strat in [self._tr("Auto-discovery"), "Автоподбор"]:
            auto_file = os.path.join(CUSTOM_STRATEGIES_DIR, "auto_found.bat")
            
            # Если файл уже существует — просто запускаем его
            if os.path.exists(auto_file):
                self.run_main_script(password)
            else:
                # Иначе запускаем процедуру поиска
                threading.Thread(
                    target=self.run_auto_discovery, args=(password,), daemon=True
                ).start()
        else:
            self.run_main_script(password)
    
    def run_auto_discovery(self, password: str) -> None:
        """Run auto-discovery in background thread."""
        self.is_auto_discovering = True
        self.set_button_busy.emit(True)
        self.status_requested.emit(
            self._tr("Discovering strategy... (please wait)"), "#FF8C00"
        )
        
        try:
            result = subprocess.run(
                ["sudo", "-S", "bash", MAIN_SCRIPT, "auto"],
                input=password + "\n",
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.status_requested.emit(
                    self._tr("Strategy discovered!"), "#107C10"
                )
                self.auto_discovery_done.emit("auto_found.bat")
            else:
                self.status_requested.emit(
                    self._tr("Auto-discovery failed"), "#ff6b6b"
                )
        except Exception as e:
            logger.error(f"Auto-discovery error: {e}")
            self.status_requested.emit(
                self._tr("Error: {error}").format(error=str(e)), "#ff6b6b"
            )
        finally:
            self.is_auto_discovering = False
            self.set_button_busy.emit(False)
    
    def on_session_changed(self, running: bool) -> None:
        """Handle session state change."""
        self.is_running = running
        if getattr(self, 'is_auto_discovering', False):
            return
        
        self.stop_loading_animation()
        self.apply_session_style(running)
    
    def run_main_script(self, password: str) -> None:
        """Run main script to start bypass."""
        try:
            subprocess.run(
                ["sudo", "-S", "bash", STOP_SCRIPT],
                input=password + "\n",
                text=True,
                check=False,
                timeout=10
            )
        except Exception:
            pass
        
        # Определяем, какую стратегию реально сохранять в конфиг
        current_selection = self.strategy_combo.currentText()
        is_auto_mode = current_selection in [self._tr("Auto-discovery"), "Автоподбор"]
        
        if is_auto_mode:
            auto_file = os.path.join(CUSTOM_STRATEGIES_DIR, "auto_found.bat")
            strategy_to_save = "auto_found.bat" if os.path.exists(auto_file) else current_selection
        else:
            strategy_to_save = current_selection

        self.config.save_strategy(strategy_to_save)
        self.config.save_game_filter(self.game_filter_enabled)
        self.config.save()
        
        self.start_loading_animation("start")
        
        try:
            proc = subprocess.Popen(
                ["sudo", "-S", "bash", MAIN_SCRIPT],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True
            )
            proc.stdin.write(password + "\n")
            proc.stdin.flush()
        except Exception as e:
            logger.error(f"Error starting main_script: {e}")
            self.show_status(self._tr("Start error"), "#ff6b6b")
            self.stop_loading_animation()
    
    def stop_session(self, password: str, stop_service: bool = False) -> None:
        """Stop bypass session."""
        try:
            if stop_service:
                logger.info("Stopping background service...")
                subprocess.run(
                    ["sudo", "-S", "systemctl", "stop", "zapretdeck.service"],
                    input=password + "\n",
                    text=True,
                    check=True,
                    timeout=15
                )
            
            subprocess.run(
                ["sudo", "-S", "bash", STOP_SCRIPT],
                input=password + "\n",
                text=True,
                check=True,
                timeout=15
            )
            self.show_status(self._tr("Stopped"), "#107C10")
        except Exception as e:
            logger.error(f"Stop error: {e}")
            self.show_status(self._tr("Stop error"), "#ff6b6b")
        finally:
            self.stop_loading_animation()
    
    def ask_sudo_password(self) -> Optional[str]:
        """Ask for sudo password."""
        if self.sudo_password:
            return self.sudo_password
        
        text, ok = QInputDialog.getText(
            self,
            self._tr("Authorization"),
            self._tr("Enter sudo password:"),
            QLineEdit.EchoMode.Password
        )
        
        if ok and text:
            res = subprocess.run(
                ["sudo", "-S", "true"],
                input=text + "\n",
                text=True,
                capture_output=True
            )
            if res.returncode == 0:
                self.sudo_password = text
                return text
            else:
                self.show_status(self._tr("Invalid password"), "#ff6b6b")
        return None
    
    def show_status(self, text: str, color: str = "#107C10") -> None:
        """Show status message."""
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 14px;"
        )
    
    def toggle_service_tile(self) -> None:
        """Toggle background service."""
        password = self.ask_sudo_password()
        if not password:
            return
        
        self.is_changing_service = True
        self.service_btn.setEnabled(False)
        self.show_status(
            self._tr("Checking service status..."), "#FF8C00"
        )
        
        try:
            currently_running = is_service_running()
            target_state = not currently_running
            action = "install" if target_state else "remove"
            
            self.show_status(
                self._tr("Enabling background mode...")
                if target_state
                else self._tr("Disabling background mode..."),
                "#FF8C00"
            )
            
            res = subprocess.run(
                ["sudo", "-S", "bash", SERVICE_SCRIPT, action],
                input=password + "\n",
                text=True,
                capture_output=True,
                timeout=40
            )
            
            if res.returncode != 0:
                error_msg = res.stderr.strip()[:150]
                logger.error(f"Service {action} failed: {error_msg}")
                self.show_status(
                    self._tr("Service error: {error}").format(
                        error=error_msg or self._tr("command failed")
                    ),
                    "#ff6b6b"
                )
                self.service_btn.setEnabled(True)
                self.is_changing_service = False
                return
            
            if target_state:
                self.show_status(self._tr("Starting service..."), "#FF8C00")
                for _ in range(15):
                    status_check = subprocess.run(
                        ["systemctl", "is-active", "--quiet", "zapretdeck.service"],
                        timeout=5
                    )
                    if status_check.returncode == 0:
                        break
                    QThread.msleep(1000)
                else:
                    self.show_status(self._tr("Service failed to start!"), "#ff6b6b")
                    self.service_btn.setEnabled(True)
                    self.is_changing_service = False
                    return
            
            self.service_btn.blockSignals(True)
            self.service_btn.setChecked(target_state)
            self.service_btn.blockSignals(False)
            self.show_status(
                self._tr("Background service enabled")
                if target_state
                else self._tr("Background service disabled"),
                "#107C10"
            )
        except Exception as e:
            logger.error(f"Service toggle exception: {e}")
            self.show_status(self._tr("Critical service error"), "#ff6b6b")
        finally:
            self.service_btn.setEnabled(True)
            self.is_changing_service = False
    
    def toggle_game_filter_tile(self) -> None:
        """Toggle game filter."""
        state = self.game_filter_btn.isChecked()
        password = self.ask_sudo_password()
        if password:
            old_state = self.game_filter_enabled
            self.game_filter_enabled = state
            self.config.save_game_filter(state)
            self.config.save()
            
            if old_state != state and self.service_btn.isChecked():
                self.show_status(
                    self._tr("Applying new filter (restarting service)..."),
                    "#FF8C00"
                )
                QTimer.singleShot(500, self.restart_background_service_silent)
            else:
                self.show_status(
                    self._tr("Game filter enabled")
                    if state
                    else self._tr("Game filter disabled"),
                    "#107C10"
                )
        else:
            self.game_filter_btn.blockSignals(True)
            self.game_filter_btn.setChecked(not state)
            self.game_filter_btn.blockSignals(False)
    
    def on_strategy_changed(self, text: str) -> None:
        """Handle strategy selection change."""
        if not text:
            return
        
        password = self.ask_sudo_password()
        if not password:
            self.strategy_combo.blockSignals(True)
            self.strategy_combo.setCurrentText(self.saved_strategy)
            self.strategy_combo.blockSignals(False)
            return
        
        old_strategy = self.saved_strategy
        
        self.config.save_strategy(text)
        self.saved_strategy = self.config.load_strategy()
        
        if old_strategy != self.saved_strategy:
            self.config.save()
            self.show_status(self._tr("Strategy saved"), "#107C10")
            
            if self.service_btn.isChecked():
                self.show_status(
                    self._tr("Applying new strategy (restarting service)..."),
                    "#FF8C00"
                )
                QTimer.singleShot(500, self.restart_background_service_silent)
        else:
            self.show_status(self._tr("Strategy saved"), "#107C10")
    
    def restart_background_service_silent(self) -> None:
        """Silently restart background service."""
        try:
            subprocess.run(
                ["sudo", "systemctl", "restart", "zapretdeck.service"],
                check=True,
                timeout=30
            )
            QTimer.singleShot(
                1000,
                lambda: self.show_status(self._tr("New setting applied"), "#107C10")
            )
        except Exception as e:
            logger.error(f"Silent service restart failed: {e}")
            self.show_status(
                self._tr("Failed to apply setting"), "#ff6b6b"
            )
    
    def on_service_changed(self, state: bool) -> None:
        """Handle service state change from monitor."""
        if getattr(self, 'is_changing_service', False):
            return
        if self.service_btn.isChecked() != state:
            self.service_btn.blockSignals(True)
            self.service_btn.setChecked(state)
            self.service_btn.blockSignals(False)
    
    def create_labeled_combo(self, label: str, items: list, current: str) -> QFrame:
        """Create a labeled combo box."""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        lbl = QLabel(label)
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        combo = QComboBox()
        combo.addItems(items)
        if current in items:
            combo.setCurrentText(current)
        layout.addWidget(lbl)
        layout.addWidget(combo)
        return frame
    
    def start_status_checker(self) -> None:
        """Start status monitoring thread."""
        self.checker = StatusChecker()
        self.checker.session_changed.connect(self.on_session_changed)
        self.checker.service_changed.connect(self.on_service_changed)
        self.checker.start()
        QTimer.singleShot(300, self.load_strategies)
    
    def show_msg(self, title: str, text: str) -> None:
        """Show message box."""
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.addButton(self._tr("OK"), QMessageBox.ButtonRole.AcceptRole)
        msg.addButton(self._tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
        msg.exec()
    
    def load_config(self) -> None:
        """Load configuration and update UI."""
        self.saved_strategy = self.config.load_strategy()
        self.game_filter_enabled = self.config.load_game_filter()
        self.load_strategies()
        self.game_filter_btn.setChecked(self.game_filter_enabled)
    
    def load_strategies(self) -> None:
        """Load and populate strategy list without showing auto_found.bat."""
        all_strategies = load_strategies()
        
        # Исключаем auto_found.bat из видимого списка
        display_strategies = [s for s in all_strategies if s != "auto_found.bat"]
        
        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        self.strategy_combo.addItem(self._tr("Auto-discovery"))
        self.strategy_combo.addItems(display_strategies)
        self.strategy_combo.blockSignals(False)
        
        # Если в конфиге сохранён auto_found.bat — показываем "Автоподбор"
        if self.saved_strategy == "auto_found.bat":
            self.strategy_combo.setCurrentText(self._tr("Auto-discovery"))
        elif self.saved_strategy in display_strategies:
            self.strategy_combo.setCurrentText(self.saved_strategy)
        else:
            self.strategy_combo.setCurrentIndex(0)
        
        self.start_btn.setEnabled(True)
    
    def check_for_update(self) -> None:
        """Check for application updates."""
        try:
            r = requests.get(
                "https://api.github.com/repos/rosakodu/zapretdeck/releases/latest",
                headers={'User-Agent': 'ZapretDeck/1.0'},
                timeout=8
            )
            data = r.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
            latest_version = version.parse(latest_tag)
            current_version = version.parse(CURRENT_VERSION)
            
            if latest_version > current_version:
                self.update_label.setText(
                    self._tr("Available: v{version}").format(version=latest_tag)
                )
                self.show_msg(
                    self._tr("Update"),
                    self._tr("New version available: v{version}\nVisit GitHub to download.").format(
                        version=latest_tag
                    )
                )
                self.version_label.setStyleSheet(
                    "font-weight: bold; font-size: 16px; color: #ff6b6b;"
                )
            else:
                self.version_label.setStyleSheet(
                    "font-weight: bold; font-size: 16px; color: #107C10;"
                )
        except Exception as e:
            logger.debug(f"Update check failed: {e}")
    
    def closeEvent(self, event) -> None:
        """Handle window close event."""
        self.loading_timer.stop()
        if hasattr(self, 'checker'):
            self.checker.stop()
            self.checker.wait()
        event.accept()