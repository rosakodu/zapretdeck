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
import time
from typing import Optional
from functools import partial
from packaging import version
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFrame, QMessageBox,
    QLineEdit, QGridLayout, QScrollArea,
    QDialog, QDialogButtonBox, QFormLayout, QCheckBox, QSpacerItem, QSizePolicy,
    QStackedWidget, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QLocale
from PyQt6.QtGui import QIcon, QCursor, QColor

from utils import (
    BASE_DIR, CUSTOM_STRATEGIES_DIR, LATEST_STRATEGIES_DIR,
    CONF_FILE, MAIN_SCRIPT, STOP_SCRIPT, RENAME_SCRIPT, SERVICE_SCRIPT,
    ICON_PATH, BUYVPN_IMAGE_PATH, HIDDEN_STRATEGIES, ConfigManager,
    check_dependencies, load_strategies, is_service_running
)
from monitor import StatusChecker
import warp
from updater import UpdateChecker, UpdaterWorker


logger = logging.getLogger(__name__)

CURRENT_VERSION = "0.2.1"

# Общие градиенты и стиль для главной и WARP кнопок (плавные современные градиенты)
_BTN_STYLE_BASE = "border-radius:12px; font-weight:bold; font-size:20px; outline:none;"
_GRAD_GREEN = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #10b981,stop:1 #34d399)"
_GRAD_ORANGE = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #f59e0b,stop:1 #fb923c)"
_GRAD_RED = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ef4444,stop:1 #f87171)"
# Интервал анимации точек: цикл … → .. → . → … за ~1.2–1.6 сек (4 кадра → 350 ms)
# Анимация точек: • → •• → ••• (цикл ~1.2–1.6 сек)
_LOADING_DOTS_INTERVAL_MS = 350
_DOTS_CYCLE = ("\u2022", "\u2022\u2022", "\u2022\u2022\u2022")


class LogMonitor(QThread):
    """Thread for monitoring log file and extracting INFO messages."""
    
    info_status_found = pyqtSignal(str)
    
    def __init__(self, log_file: str):
        super().__init__()
        self.log_file = log_file
        self._running = True
        self._last_position = 0
    
    def stop(self) -> None:
        """Stop the log monitoring thread."""
        self._running = False
    
    def run(self) -> None:
        """Main log monitoring loop."""
        while self._running:
            try:
                if os.path.exists(self.log_file):
                    with open(self.log_file, 'r', encoding='utf-8') as f:
                        # Seek to last position to avoid re-reading
                        f.seek(self._last_position)
                        new_lines = f.readlines()
                        
                        # Update last position
                        if new_lines:
                            self._last_position = f.tell()
                        
                        # Process new lines
                        for line in new_lines:
                            line = line.strip()
                            # Look for [INFO] warp pattern - extract text after ':'
                            if '[info] warp:' in line.lower():
                                # Extract text after ':' and strip whitespace
                                parts = line.split(':', 1)
                                if len(parts) > 1:
                                    status_text = parts[1].strip()
                                    if status_text:
                                        self.info_status_found.emit(status_text)
                
                self.msleep(500)  # Check every 500ms
            except Exception as e:
                logger.error(f"LogMonitor error: {e}")
                self.msleep(1000)


class ZapretGUI(QMainWindow):
    """Main GUI window for ZapretDeck."""
    
    status_requested = pyqtSignal(str, str)
    auto_discovery_done = pyqtSignal(str)
    set_button_busy = pyqtSignal(bool)
    
    def __init__(self, translator=None):
        super().__init__()
        self.translator = translator
        
        self.setWindowTitle(self._tr("ZapretDeck"))
        # В Hyprland используем resize для плиточного режима, иначе setFixedSize
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            self.resize(1280, 800)
        else:
            self.setFixedSize(1280, 800)
        self.setObjectName("zapretdeck")
        self.setProperty("WM_CLASS", "zapretdeck")
        
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        
        self.sudo_password: Optional[str] = None
        self._password_prompt_in_progress = False
        self.config = ConfigManager()
        self.saved_strategy = self.config.load_strategy()
        self.game_filter_enabled = self.config.load_game_filter()
        self.is_running = False
        self.is_changing_service = False
        self.is_auto_discovering = False
        self.is_changing_warp = False
        self.is_registering_warp = False  # Tracks if background registration is in progress
        self.warp_is_connected = False
        self.warp_is_registered = False  # Tracks if WARP is registered and verified
        self._warp_reg_animation_active = False  # Tracks if WARP registration animation is playing
        self.warp_installed = warp.is_warp_installed()
        # Краткая "заморозка" управления после операций WARP,
        # чтобы дать демону и сети стабилизироваться.
        self.warp_cooldown_active = False
        # Время последнего успешного подключения WARP — не перезаписывать статус на False в течение 12 сек
        self._warp_connect_success_at: Optional[float] = None
        # Кулдаун для основной кнопки START/STOP.
        self.start_cooldown_active = False
        # Флаги удержания оранжевого статуса на 3 секунды
        self.is_start_loading_delayed = False
        self.is_warp_loading_delayed = False
        # Счётчик и базовый текст для анимации точек на главной кнопке.
        self.loading_dots = 0
        self.start_loading_base_text = ""
        # Направление текущей операции (True - подключение, False - отключение)
        self.is_connecting_strategy: Optional[bool] = None
        # Целевое состояние после завершения анимации (чтобы избежать "дребезга")
        self._start_loading_target_state: Optional[bool] = None
        # Счётчик и базовый текст для анимации точек на WARP (CONNECT / DISCONNECT).
        self.warp_loading_dots = 0
        self.warp_loading_base_text = ""
        self.loading_timer = QTimer()
        self.loading_timer.timeout.connect(self.update_loading_animation)
        self.warp_timer = QTimer()
        self.warp_timer.timeout.connect(self.update_warp_loading_animation)

        # Флаги для WARP переходных состояний
        self._warp_connecting = False
        self._warp_disconnecting = False
        self._warp_loading_target_state: Optional[bool] = None
        
        # --- Инерция статуса (защита от дребезга) ---
        self._last_effective_running_state: Optional[bool] = None
        self._last_state_lock_time: float = 0.0
        self._last_warp_effective_state: Optional[bool] = None
        self._last_warp_lock_time: float = 0.0
        
        self.is_starting_session = False
        self.is_stopping_session = False
        self._transition_lock_until: float = 0.0  # Время до которого блокируем обновления UI
        self._locked_state: Optional[bool] = None  # Состояние которое мы блокируем (защита от дребезга)
        
        # Флаг начальной синхронизации - блокируем сигналы от StatusChecker до завершения
        self._initial_sync_done = False

        # Запускаем мониторинг логов для вывода статусов [INFO] warp
        self.start_log_monitor()
        self.start_status_checker()
        
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
        # self.start_status_checker() is already called after basic setup
        QTimer.singleShot(300, self.handle_startup_tasks)
        QTimer.singleShot(1000, self.check_for_update)
        QTimer.singleShot(2000, self.sync_service_button_on_startup)
        # Даём больше времени сервису после ребута (1.5s + 4s повт.) — иначе UI считает что не запущено
        QTimer.singleShot(1500, self.sync_initial_state)
        QTimer.singleShot(5000, self.sync_initial_state)
        QTimer.singleShot(10000, self.sync_initial_state)
        
        self.status_requested.connect(self.show_status)
        self.auto_discovery_done.connect(self.on_auto_success)
        self.set_button_busy.connect(self.update_button_loading_state)
        
        self.show_status(self._tr("Ready to work!"), "#10b981")
    
    def _tr(self, text: str) -> str:
        if self.translator:
            translated = QApplication.translate("ZapretGUI", text)
            return translated if translated else text
        return text
    
    def handle_startup_tasks(self) -> None:
        """Tasks to perform after startup: ask for sudo password if not showing info."""
        if not self.config.load_show_info():
            self.ask_sudo_password()

    def create_info_page(self) -> QWidget:
        """Create the integrated info page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)
        
        # Info Text
        info_label = QLabel()
        info_text = self._tr(
            "ZapretDeck — это лёгкий и удобный инструмент для обхода интернет-блокировок "
            "на Steam Deck и других Linux-системах.\n\n"
            "WARP помогает защитить ваше интернет-соединение: он шифрует трафик между "
            "устройством и сетью Cloudflare, повышая приватность и безопасность. "
            "Особенно будет полезен для онлайн-игр.\n\n"
            "• WARP будет работать только если он установлен и активирован в системе.\n\n"
            "• Перед запуском приложения убедитесь, что любой другой VPN-сервис отключён на устройстве.\n\n"
            "• На атомарных дистрибутивах (например, SteamOS) WARP может удаляться "
            "после обновлений системы. Если это произошло — просто установите его снова.\n\n"
            "Если Steam Deck зависает на логотипе Steam при включении — попробуйте временно отключить Wi-Fi.\n\n"
            "Если возникнут вопросы или сложности — заглядывайте в сообщество проекта. "
            "Будем рады помочь 🙂"
        )
        info_label.setText(info_text)
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-size: 16px; line-height: 1.5; color: white;")
        
        # Add black outline effect using drop shadow
        outline = QGraphicsDropShadowEffect()
        outline.setBlurRadius(0)
        outline.setColor(QColor(0, 0, 0))
        outline.setOffset(1, 1)
        info_label.setGraphicsEffect(outline)
        
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        # Checkbox "Don't show again"
        self.dont_show_checkbox = QCheckBox(self._tr("Don't show again"))
        self.dont_show_checkbox.setStyleSheet("font-size: 15px; color: #10b981; font-weight: bold;")
        layout.addWidget(self.dont_show_checkbox)
        
        # OK Button
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton(self._tr("OK"))
        ok_btn.setMinimumHeight(64)
        ok_btn.setMinimumWidth(200)
        ok_btn.setStyleSheet(f"color:#fff; background:{_GRAD_GREEN}; {_BTN_STYLE_BASE}")
        ok_btn.clicked.connect(self.on_info_accepted)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        return page

    def on_info_accepted(self) -> None:
        """Handle OK button click on the info page."""
        if hasattr(self, "dont_show_checkbox") and self.dont_show_checkbox.isChecked():
            self.config.save_show_info(False)
            self.config.save()
        
        self.stacked_widget.setCurrentWidget(self.main_page)
        self.ask_sudo_password()

    
    def sync_initial_state(self) -> None:
        """Sync all buttons to real system state on startup/restart."""
        try:
            # 1. Check nfqws process (main strategy)
            running = subprocess.run(
                ["pgrep", "-f", "nfqws"],
                capture_output=True
            ).returncode == 0

            if running != self.is_running:
                logger.info(f"Initial state sync: is_running {self.is_running} → {running}")
                self.is_running = running
                self.apply_session_style(running)

            # If we were showing "подключение" but nfqws is already running (e.g. after reboot,
            # StatusChecker was slow or missed the transition) — complete the transition now
            if running and self.is_starting_session:
                logger.info("Initial sync: nfqws already running while START was pending, completing transition")
                self.is_starting_session = False
                if self.loading_timer.isActive():
                    self.loading_timer.stop()
                self._start_loading_target_state = True
                self._last_effective_running_state = True
                self._last_state_lock_time = time.time()
                self.is_start_loading_delayed = False
                self.is_connecting_strategy = None
                self._locked_state = True
                self._transition_lock_until = time.time() + 5.0
                self.start_btn.setEnabled(True)
                self.start_btn.setText(self._tr("STOP"))
                self.start_btn.setStyleSheet(f"color:#fff; background:{_GRAD_RED}; {_BTN_STYLE_BASE}")

            # 2. Check WARP status
            if self.warp_installed:
                # Check connection status
                is_connected, _ = warp.get_warp_status()
                if is_connected != self.warp_is_connected:
                    logger.info(f"Initial state sync: warp_is_connected {self.warp_is_connected} → {is_connected}")
                    self.warp_is_connected = is_connected

                # Check registration status
                is_registered, _ = warp.verify_warp_registration(retries=2)
                if is_registered != self.warp_is_registered:
                    logger.info(f"Initial state sync: warp_is_registered {self.warp_is_registered} → {is_registered}")
                    self.warp_is_registered = is_registered

                self.update_warp_button_style()

            # Mark initial sync as complete - now allow StatusChecker signals
            self._initial_sync_done = True
            logger.info("Initial state sync completed")

        except Exception as e:
            logger.error(f"Initial state sync error: {e}")

    def sync_service_button_on_startup(self) -> None:
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
        """Главная кнопка при автоподборе: CONNECT (оранжевый) + анимация точек … → .. → . → …."""
        if is_busy:
            self.start_loading_animation(connecting=True)
        else:
            if self.loading_timer.isActive():
                self.loading_timer.stop()
            QTimer.singleShot(0, self._reset_button_state)

    def _reset_button_state(self) -> None:
        """Reset button to normal state."""
        # Не сбрасываем кнопку во время переходных состояний
        if self.is_starting_session or self.is_stopping_session:
            return
        
        self.start_btn.setEnabled(True)
        # УБРАНО: self.start_btn.setStyleSheet("") - это вызывало вспышку цвета
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
        self.setStyleSheet("""
            QPushButton, QComboBox, QAbstractItemView {
                outline: none;
            }
            QPushButton:focus, QComboBox:focus {
                outline: none;
            }
        """)

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        self.info_page = self.create_info_page()
        self.main_page = self.create_main_page()
        
        self.stacked_widget.addWidget(self.info_page)
        self.stacked_widget.addWidget(self.main_page)
        
        # Set initial page immediately to avoid flicker
        if self.config.load_show_info():
            self.stacked_widget.setCurrentWidget(self.info_page)
        else:
            self.stacked_widget.setCurrentWidget(self.main_page)

    def create_main_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        scroll.setWidget(container)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        top = QFrame()
        top.setProperty("class", "card")
        top.setMinimumHeight(120)
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(16, 16, 16, 16)
        
        self.version_label = QLabel(f"v{CURRENT_VERSION}")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.version_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #10b981;")
        top_layout.addWidget(self.version_label)
        
        combo_frame = self.create_labeled_combo(
            self._tr("Current bypass strategy:"), [], ""
        )
        self.strategy_combo = combo_frame.findChild(QComboBox)
        self.strategy_combo.setObjectName("strategy_combo")
        self.strategy_combo.currentTextChanged.connect(self.on_strategy_changed)
        top_layout.addWidget(combo_frame)
        
        layout.addWidget(top)
        
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setMinimumHeight(1)
        layout.addWidget(sep)
        
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
            QPushButton:checked {
                background: %GRAD_GREEN%;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #444444;
            }
        """
        
        self.service_btn = QPushButton(self._tr("Background Service"))
        self.service_btn.setCheckable(True)
        self.service_btn.setStyleSheet(tile_style.replace("%GRAD_GREEN%", _GRAD_GREEN))
        self.service_btn.clicked.connect(self.toggle_service_tile)
        
        self.game_filter_btn = QPushButton(self._tr("Game Filter"))
        self.game_filter_btn.setCheckable(True)
        self.game_filter_btn.setStyleSheet(tile_style.replace("%GRAD_GREEN%", _GRAD_GREEN))
        self.game_filter_btn.clicked.connect(self.toggle_game_filter_tile)
        
        tiles_layout.addWidget(self.service_btn, 1)
        tiles_layout.addWidget(self.game_filter_btn, 1)
        
        layout.addWidget(tiles_frame)
        
        self.start_btn = QPushButton(self._tr("START"))
        self.start_btn.setMinimumHeight(64)
        self.start_btn.clicked.connect(self.start_zapret)
        self.apply_session_style(False)
        layout.addWidget(self.start_btn)
        
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
            btn.setMinimumHeight(44)
            btn.clicked.connect(lambda _, u=url: webbrowser.open(u))
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            actions_layout.addWidget(btn, i // 2, i % 2)
        
        layout.addWidget(actions_card)
        
        # Кнопка WARP - скрыта при запуске (показывается только когда стратегия активна)
        self.warp_btn = QPushButton(self._tr("WARP"))
        self.warp_btn.setMinimumHeight(64)
        self.warp_btn.clicked.connect(self.toggle_warp)
        self.warp_btn.setVisible(False)  # Скрываем пока стратегия не запущена
        self.update_warp_button_style()
        layout.addWidget(self.warp_btn)

        exit_btn = QPushButton(self._tr("Exit"))
        exit_btn.setMinimumHeight(56)
        exit_btn.clicked.connect(self.close)
        exit_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(exit_btn)
        
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px;")
        self.status_label.setMinimumHeight(30)
        layout.addWidget(self.status_label)
        
        # Info status label for displaying [INFO] warp messages
        self.info_status_label = QLabel("")
        self.info_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_status_label.setStyleSheet("font-size: 12px; color: #888888;")
        self.info_status_label.setMinimumHeight(20)
        self.info_status_label.setWordWrap(True)
        layout.addWidget(self.info_status_label)
        
        # Buy VPN banner - ABOVE status
        self.buyvpn_btn = QPushButton(self._tr("Buy VPN"))
        self.buyvpn_btn.setMinimumHeight(64)
        self.buyvpn_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.buyvpn_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.buyvpn_btn.setStyleSheet(f"color:#fff; background:{_GRAD_GREEN}; {_BTN_STYLE_BASE}")
        self.buyvpn_btn.clicked.connect(lambda: webbrowser.open("https://vk.com/valvesteamdeck?w=donut_payment-199643211&levelId=1661"))
        self.buyvpn_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if os.path.exists(BUYVPN_IMAGE_PATH):
            self.buyvpn_btn.setStyleSheet(
                f"QPushButton {{ border-image: url({BUYVPN_IMAGE_PATH}); "
                f"border: none; {_BTN_STYLE_BASE} }} "
                f"QPushButton:hover {{ background-color: rgba(16, 185, 129, 0.3); border-radius: 12px; }}"
            )
        layout.addSpacing(20)
        layout.addWidget(self.buyvpn_btn)
        
        
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
        return scroll
    
    def apply_session_style(self, running: bool) -> None:
        """Главная кнопка: START (зелёный) или STOP (красный), без анимации."""
        # 0. Блокировка во время изменения сервиса
        if self.is_changing_service:
            return
        
        # 1. СТРОЖАЙШАЯ блокировка во время оранжевого перехода
        if self.loading_timer.isActive() or self.is_start_loading_delayed:
            text = self.start_loading_base_text or (self._tr("CONNECT") if self.is_connecting_strategy is not False else self._tr("DISCONNECT"))
            self.start_btn.setText(text)
            self.start_btn.setStyleSheet(f"color:#fff; background:{_GRAD_ORANGE}; {_BTN_STYLE_BASE}")
            return

        # 2. Блокировка во время переходного состояния (запуск/остановка сессии)
        if self.is_starting_session or self.is_stopping_session:
            # Не меняем кнопку, пока идёт переходное состояние
            return

        # 3. Инерция: если мы в периоде стабилизации (5с), принудительно используем захваченное состояние
        if time.time() - self._last_state_lock_time < 5.0 and self._last_effective_running_state is not None:
            running = self._last_effective_running_state

        # 4. Кулдаун после нажатия
        if self.is_auto_discovering or self.start_cooldown_active:
             # Не возвращаемся досрочно, если нужно просто обновить ЦВЕТ под блокировкой кулдауна.
             # Но если мы НЕ в инерции и НЕ в анимации, позволяем обновить стиль,
             # просто кнопка останется disabled.
             pass

        text = self._tr("STOP") if running else self._tr("START")
        grad = _GRAD_RED if running else _GRAD_GREEN
        self.start_btn.setText(text)
        self.start_btn.setStyleSheet(f"color:#fff; background:{grad}; {_BTN_STYLE_BASE}")
    
    def start_loading_animation(self, connecting: bool) -> None:
        """Главная кнопка: CONNECT или DISCONNECT (оранжевый градиент) + анимация … → .. → . → … только во время надписи."""
        # СБРАСЫВАЕМ все флаги задержки и инерции при новом запуске анимации, 
        # чтобы старые состояния не мешали новому процессу.
        self.is_start_loading_delayed = False
        self._last_state_lock_time = 0.0
        self._last_effective_running_state = None
        
        self.is_connecting_strategy = connecting
        self.loading_dots = 0
        self.start_loading_base_text = self._tr("CONNECT") if connecting else self._tr("DISCONNECT")
        self.start_btn.setText(f"{self.start_loading_base_text}{_DOTS_CYCLE[0]}")
        self.start_btn.setEnabled(False)
        self.start_btn.setStyleSheet(f"color:#fff; background:{_GRAD_ORANGE}; {_BTN_STYLE_BASE}")
        self.loading_timer.start(_LOADING_DOTS_INTERVAL_MS)

    def update_loading_animation(self) -> None:
        """Анимация точек для главной кнопки: ••• → •• → • (цикл ~1.2–1.6 сек)."""
        self.loading_dots = (self.loading_dots + 1) % 3
        base = self.start_loading_base_text or self._tr("CONNECT")
        self.start_btn.setText(f"{base}{_DOTS_CYCLE[self.loading_dots]}")
    
    def stop_loading_animation(self, final_state: Optional[bool] = None) -> None:
        """Остановить анимацию и запустить 3-сек задержку оранжевого."""
        if self.is_start_loading_delayed:
            return

        target = final_state if final_state is not None else self.is_running
        self._start_loading_target_state = target
        
        # ЗАХВАТЫВАЕМ состояние для инерции МГНОВЕННО (на 5 секунд + 3 сек задержки)
        self._last_effective_running_state = target
        self._last_state_lock_time = time.time()
        
        # Удерживаем оранжевый статус ещё 3 секунды - НЕ останавливаем таймер!
        # Анимация точек продолжается до конца задержки
        self.is_start_loading_delayed = True
        logger.info(f"Holding orange status (target={target}) for 3 seconds...")
        QTimer.singleShot(3000, self._actually_stop_loading_animation)

    def _actually_stop_loading_animation(self) -> None:
        """Окончательная остановка анимации после задержки."""
        self.is_start_loading_delayed = False
        
        target_state = self._start_loading_target_state
        
        # ЗАХВАТЫВАЕМ состояние для инерции (на 5 секунд)
        import time
        self._last_effective_running_state = target_state
        self._last_state_lock_time = time.time()
        
        self.is_connecting_strategy = None
        self._start_loading_target_state = None

        # Останавливаем таймер здесь (через 3 секунды после начала задержки)
        if self.loading_timer.isActive():
            self.loading_timer.stop()
        self.start_btn.setEnabled(True)
    
        final_running = target_state if target_state is not None else self.is_running
        self.apply_session_style(final_running)

    def _start_start_cooldown(self, ms: int = 3000) -> None:
        """Кулдаун главной кнопки: кнопка отключена, стиль зависит от состояния."""
        if self.start_cooldown_active:
            return
        self.start_cooldown_active = True
        self.start_btn.setEnabled(False)
        
        # Если активна задержка оранжевого статуса, НЕ меняем стиль здесь.
        # Стиль будет обновлён в _actually_stop_loading_animation.
        if not self.is_start_loading_delayed:
            self.apply_session_style(self.is_running)

        QTimer.singleShot(ms, self._end_start_cooldown)

    def _end_start_cooldown(self) -> None:
        """Завершить cooldown и вернуть кнопке START/STOP обычное состояние."""
        self.start_cooldown_active = False
        self.start_btn.setEnabled(True)
        # Если в данный момент активно оранжевое удержание, apply_session_style 
        # сама решит не менять стиль.
        self.apply_session_style(self.is_running)
    
    # ──────────────────────────────────────────────
    #                WARP БЛОК
    # ──────────────────────────────────────────────
    
    def update_warp_button_style(self) -> None:
        """
        Кнопка WARP:
        - Скрыта когда стратегия не запущена
        - WARP РЕГИСТРАЦИЯ + анимация ••• •• • - во время регистрации
        - WARP START (зелёный) — без анимации
        - CONNECT / DISCONNECT (оранжевый) + анимация точек — только во время операции
        - WARP STOP (красный) — без анимации
        """
        # 0. Если стратегия не запущена - скрываем кнопку WARP полностью
        if not self.is_running:
            self.warp_btn.setVisible(False)
            return
        
        # Показываем кнопку когда стратегия запущена
        self.warp_btn.setVisible(True)

        # 1. СТРОЖАЙШАЯ блокировка во время оранжевого перехода
        if self.warp_timer.isActive() or self.is_warp_loading_delayed:
            text = self.warp_loading_base_text or (self._tr("DISCONNECT") if self._warp_disconnecting else self._tr("CONNECT"))
            self.warp_btn.setText(text)
            self.warp_btn.setStyleSheet(f"color:#fff; background:{_GRAD_ORANGE}; {_BTN_STYLE_BASE}")
            return
        
        # 2. Проверка установки и регистрации - показываем анимацию регистрации
        trans = "color:#fff; background:transparent; " + _BTN_STYLE_BASE
        if not self.warp_installed:
            self.warp_btn.setStyleSheet(trans)
            self.warp_btn.setEnabled(False)
            self.warp_btn.setText(self._tr("WARP is not installed"))
            return
        if not self.warp_is_registered:
            # Показываем анимацию регистрации
            self.warp_btn.setEnabled(False)
            self.warp_btn.setStyleSheet(f"color:#fff; background:{_GRAD_ORANGE}; {_BTN_STYLE_BASE}")
            # Если таймер анимации регистрации не запущен - запускаем
            if not hasattr(self, '_warp_reg_animation_active') or not self._warp_reg_animation_active:
                self._warp_reg_animation_active = True
                self._start_warp_registration_animation()
            return

        # Останавливаем анимацию регистрации если она была
        if hasattr(self, '_warp_reg_animation_active') and self._warp_reg_animation_active:
            self._warp_reg_animation_active = False
            if hasattr(self, '_warp_reg_timer') and self._warp_reg_timer.isActive():
                self._warp_reg_timer.stop()

        # 3. Кулдаун: без анимации, отключена. Стиль зависит от состояния (Зелёный/Красный/Оранжевый).
        if self.warp_cooldown_active:
            self.warp_btn.setEnabled(False)
            # Если активна задержка оранжевого статуса, сохраняем оранжевый стиль.
            if self.is_warp_loading_delayed:
                self.warp_btn.setStyleSheet(f"color:#fff; background:{_GRAD_ORANGE}; {_BTN_STYLE_BASE}")
            else:
                # В обычном кулдауне показываем целевое состояние
                if self.warp_is_connected:
                    self.warp_btn.setText(self._tr("WARP STOP"))
                    self.warp_btn.setStyleSheet(f"color:#fff; background:{_GRAD_RED}; {_BTN_STYLE_BASE}")
                else:
                    self.warp_btn.setText(self._tr("WARP START"))
                    self.warp_btn.setStyleSheet(f"color:#fff; background:{_GRAD_GREEN}; {_BTN_STYLE_BASE}")
            return

        self.warp_btn.setEnabled(True)
        # WARP STOP (красный)
        if self.warp_is_connected:
            self.warp_btn.setStyleSheet(f"color:#fff; background:{_GRAD_RED}; {_BTN_STYLE_BASE}")
            self.warp_btn.setText(self._tr("WARP STOP"))
            return
        # WARP START (зелёный)
        self.warp_btn.setStyleSheet(f"color:#fff; background:{_GRAD_GREEN}; {_BTN_STYLE_BASE}")
        self.warp_btn.setText(self._tr("WARP START"))

    def _start_warp_registration_animation(self) -> None:
        """Анимация WARP РЕГИСТРАЦИЯ с точками ••• •• •"""
        if not hasattr(self, '_warp_reg_timer'):
            self._warp_reg_timer = QTimer()
            self._warp_reg_timer.timeout.connect(self._update_warp_registration_animation)

        self._warp_reg_dots = 0
        self._warp_reg_timer.start(_LOADING_DOTS_INTERVAL_MS)
        # Установим начальный текст
        self.warp_btn.setText(f"{self._tr('WARP РЕГИСТРАЦИЯ')}{_DOTS_CYCLE[0]}")

    def _update_warp_registration_animation(self) -> None:
        """Обновление анимации WARP РЕГИСТРАЦИЯ"""
        if not hasattr(self, '_warp_reg_animation_active') or not self._warp_reg_animation_active:
            if hasattr(self, '_warp_reg_timer') and self._warp_reg_timer.isActive():
                self._warp_reg_timer.stop()
            return

        # Если WARP уже зарегистрирован - останавливаем анимацию
        if self.warp_is_registered:
            self._warp_reg_animation_active = False
            self._warp_reg_timer.stop()
            self.update_warp_button_style()
            return

        self._warp_reg_dots = (self._warp_reg_dots + 1) % 3
        self.warp_btn.setText(f"{self._tr('WARP РЕГИСТРАЦИЯ')}{_DOTS_CYCLE[self._warp_reg_dots]}")

    
    def start_warp_loading_animation(self, connecting: bool) -> None:
        """WARP кнопка: CONNECT или DISCONNECT (оранжевый) + анимация … → .. → . → … только во время надписи."""
        if self.warp_timer.isActive():
            logger.warning("WARP timer already active, not starting new animation")
            return
        
        # Сбрасываем флаг задержки при новом запуске
        self.is_warp_loading_delayed = False
        
        self.warp_loading_dots = 0
        self.warp_loading_base_text = self._tr("CONNECT") if connecting else self._tr("DISCONNECT")
        self._warp_connecting = connecting
        self._warp_disconnecting = not connecting
        self.warp_btn.setText(f"{self.warp_loading_base_text}{_DOTS_CYCLE[0]}")
        self.warp_btn.setEnabled(False)
        self.warp_btn.setStyleSheet(f"color:#fff; background:{_GRAD_ORANGE}; {_BTN_STYLE_BASE}")
        self.warp_timer.start(_LOADING_DOTS_INTERVAL_MS)
        
    def update_warp_loading_animation(self) -> None:
        """Анимация точек для WARP: ••• → •• → • (тот же стиль и скорость, что у главной кнопки)."""
        self.warp_loading_dots = (self.warp_loading_dots + 1) % 3
        base = self.warp_loading_base_text or self._tr("CONNECT")
        self.warp_btn.setText(f"{base}{_DOTS_CYCLE[self.warp_loading_dots]}")
    
    def stop_warp_loading_animation(self) -> None:
        """Stop loading animation for WARP button."""
        if self.is_warp_loading_delayed:
            logger.debug("WARP already delaying, skipping stop")
            return
        
        # Устанавливаем целевое состояние
        self._warp_loading_target_state = self.warp_is_connected
        
        # Удерживаем оранжевый статус ещё 3 секунды - НЕ останавливаем таймер!
        # Анимация точек продолжается до конца задержки
        self.is_warp_loading_delayed = True
        logger.info("Holding orange status (WARP) for 3 seconds...")
        QTimer.singleShot(3000, self._actually_stop_warp_loading_animation)

    def _actually_stop_warp_loading_animation(self) -> None:
        """Окончательная остановка анимации WARP после задержки."""
        self.is_warp_loading_delayed = False
        self._warp_connecting = False
        self._warp_disconnecting = False
        self._warp_loading_target_state = None

        # Останавливаем таймер здесь (через 3 секунды после начала задержки)
        if self.warp_timer.isActive():
            self.warp_timer.stop()
        
        # Переводим кнопку обратно в обычное состояние.
        # Если активен cooldown, отдельная логика управления доступностью
        # сработает позже в _update_controls_for_warp_cooldown.
        if not self.warp_cooldown_active:
            self.warp_btn.setEnabled(True)
        self.update_warp_button_style()

    def _update_controls_for_warp_cooldown(self) -> None:
        """
        Включить/выключить основные кнопки управления на время короткого cooldown
        после операций WARP, чтобы предотвратить "дёргание" демона.
        """
        buttons = [getattr(self, name, None) for name in ("warp_btn", "start_btn", "service_btn", "game_filter_btn")]
        buttons = [b for b in buttons if b is not None]

        if self.warp_cooldown_active:
            for btn in buttons:
                btn.setEnabled(False)
        else:
            # Возвращаем кнопкам возможность быть нажатыми,
            # остальное (цвета/текст) решают их собственные методы.
            if hasattr(self, "start_btn"):
                self.start_btn.setEnabled(True)
            if hasattr(self, "service_btn"):
                self.service_btn.setEnabled(True)
            if hasattr(self, "game_filter_btn"):
                self.game_filter_btn.setEnabled(True)
            # Стиль и доступность WARP зависят от её состояния
            self.update_warp_button_style()

    def _start_warp_cooldown(self, ms: int = 5000) -> None:
        """Запустить короткий cooldown после операций WARP: кнопка отключена, стиль сохраняется оранжевым если идет delay."""
        if self.warp_cooldown_active:
            return
        self.warp_cooldown_active = True
        
        # Если идет задержка оранжевого, не трогаем стиль, он обновится потом
        if not self.is_warp_loading_delayed:
            self.update_warp_button_style()
            
        self._update_controls_for_warp_cooldown()
        QTimer.singleShot(ms, self._end_warp_cooldown)

    def _end_warp_cooldown(self) -> None:
        """Завершить cooldown и вернуть управление пользователю."""
        self.warp_cooldown_active = False
        self._update_controls_for_warp_cooldown()
    
    def toggle_warp(self) -> None:
        """Handle WARP button click - ONLY for connect/disconnect.
        
        Registration happens automatically in background when strategy connects.
        This button is ONLY for connecting/disconnecting WARP.
        """
        # Ignore clicks during operations or cooldown
        if self.is_changing_warp or self.is_auto_discovering or self.loading_timer.isActive() or self.warp_cooldown_active:
            logger.info("WARP operation already in progress, ignoring click")
            return
        
        if not self.warp_installed:
            self.show_status(self._tr("WARP не установлен"), "#ff6b6b")
            return
        
        # Must be registered to use this button (registration happens in background)
        if not self.warp_is_registered:
            self.show_status(self._tr("WARP not registered yet"), "#ff6b6b")
            return
        
        # Strategy must be running
        if not self.is_running:
            self.show_status(self._tr("Start strategy first"), "#ff6b6b")
            return
        
        password = self.ask_sudo_password()
        if not password:
            return
        
        # If connected → disconnect
        if self.warp_is_connected:
            self.is_changing_warp = True
            logger.info("Starting WARP disconnect...")
            self.start_warp_loading_animation(connecting=False)
            
            def warp_disconnect_task():
                success, msg = False, ""
                try:
                    success, msg = warp.disconnect_warp()
                    logger.info(f"WARP disconnect result: success={success}, msg={msg}")
                except Exception as e:
                    logger.error(f"WARP disconnect error: {e}")
                    success, msg = False, str(e)
                finally:
                    QTimer.singleShot(100, partial(self._on_warp_finished, "disconnect", success, msg))

            threading.Thread(target=warp_disconnect_task, daemon=True).start()
            return
        
        # If not connected → connect (start service + mode + connect)
        else:
            self.is_changing_warp = True
            logger.info("Starting WARP connection...")
            self.start_warp_loading_animation(connecting=True)

            def warp_connect_task():
                success = False
                msg = ""
                try:
                    # Step 0: убедиться, что сервис warp-svc запущен (без него warp-cli не работает)
                    start_ok, _ = warp.start_warp_service(password)
                    if not start_ok:
                        logger.warning("WARP service start failed or already running, continuing...")
                    # Step 1: Set mode (не критично при ошибке)
                    logger.info("Setting WARP mode to warp+doh...")
                    warp.set_warp_mode()
                    # Step 2: Connect
                    logger.info("Connecting to WARP...")
                    success, msg = warp.connect_warp()
                    logger.info(f"WARP connect result: success={success}, msg={msg}")
                except Exception as e:
                    logger.error(f"WARP connection error: {e}")
                    success, msg = False, str(e)
                finally:
                    # Всегда уведомляем главный поток, чтобы снять анимацию и обновить UI
                    QTimer.singleShot(100, partial(self._on_warp_finished, "connect", success, msg))

            threading.Thread(target=warp_connect_task, daemon=True).start()
            return
    
    
    def _on_warp_finished(self, operation: str, success: bool, msg: str) -> None:
        """
        Handle WARP operation completion - called from main thread via QTimer.singleShot.

        `operation` can be: "connect" or "disconnect"
        """
        logger.info(f"_on_warp_finished called: operation={operation}, success={success}, msg={msg}")

        if success:
            op = (operation or "").lower()
            
            if op == "connect":
                # Connection successful - mark as connected
                self.warp_is_connected = True
                self.warp_is_registered = True  # Ensure registered flag is set
                self._warp_connect_success_at = time.time()  # защита от ложного "Disconnected" в check_warp_status
                self.show_status(self._tr("WARP connected"), "#107C10")
                
            elif op == "disconnect":
                # Disconnect + registration delete — теперь WARP не зарегистрирован
                self.warp_is_connected = False
                self.warp_is_registered = False
                self._warp_connect_success_at = None
                self.show_status(self._tr("WARP disconnected"), "#107C10")

            self.update_warp_button_style()
        else:
            # Error handling with specific messages
            op = (operation or "").lower()
            if op == "connect":
                self.show_status(self._tr("Connection failed"), "#ff6b6b")
            elif op == "disconnect":
                self.show_status(self._tr("Disconnect failed"), "#ff6b6b")
            else:
                self.show_status(self._tr("ERROR"), "#ff6b6b")

        self.is_changing_warp = False
        self.stop_warp_loading_animation()
        # Короткая задержка, чтобы дать демону и сети "успокоиться"
        # перед следующей попыткой переключения.
        self._start_warp_cooldown()


    # ──────────────────────────────────────────────
    #                ОСНОВНАЯ ЛОГИКА ЗАПУСКА
    # ──────────────────────────────────────────────
    
    def start_zapret(self) -> None:
        # Игнорируем нажатия, если уже идёт запуск/остановка,
        # автоподбор или операция WARP / cooldown.
        if (
            self.loading_timer.isActive()
            or self.is_auto_discovering
            or self.is_changing_warp
            or self.warp_cooldown_active
            or self.start_cooldown_active
        ):
            return
        
        password = self.ask_sudo_password()
        if not password:
            return
        
        if self.is_running:
            self.start_loading_animation(connecting=False)
            self.update_warp_button_style()  # Сразу отключаем кнопку WARP визуально
            QTimer.singleShot(100, lambda: self.stop_session(password, self.service_btn.isChecked()))
            return
        
        current_strat = self.strategy_combo.currentText()
        
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
    
    def run_main_script(self, password: str) -> None:
        # МГНОВЕННО включаем оранжевую индикацию и ставим флаг запуска.
        self.is_starting_session = True
        # Очищаем инфо-статус при запуске новой сессии
        self.info_status_label.setText("")
        self.start_loading_animation(connecting=True)
        
        try:
            # Останавливаем предыдущую сессию, если была
            subprocess.run(
                ["sudo", "-S", "bash", STOP_SCRIPT],
                input=password + "\n",
                text=True,
                check=False,
                timeout=10
            )
        except Exception:
            pass

        # No need to call start_warp_service here anymore, 
        # it will be called on-demand by registration or connection logic
        # if the service is found to be down.
        
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
            proc.stdin.close()
        except Exception as e:
            logger.error(f"Error starting main_script: {e}")
            self.show_status(self._tr("Start error"), "#ff6b6b")
            self.stop_loading_animation()
            return

        # Таймер статуса обновит кнопку на STOP при обнаружении запущенного процесса
        # Fallback: если через 15 с всё ещё "подключение" — принудительная проверка (на случай долгого старта/ребута)
        QTimer.singleShot(15000, self._fallback_check_session_after_start)

    def _fallback_check_session_after_start(self) -> None:
        """Если после Start прошло 15 с и UI всё ещё в режиме CONNECT — проверить состояние."""
        if not (self.is_starting_session and self.loading_timer.isActive()):
            return
        try:
            running = subprocess.run(
                ["pgrep", "-f", "nfqws"],
                capture_output=True
            ).returncode == 0
            if running:
                self.is_running = True
                self.is_starting_session = False
                if self.loading_timer.isActive():
                    self.loading_timer.stop()
                self.stop_loading_animation(True)
        except Exception:
            pass

    def stop_session(self, password: str, stop_service: bool = False) -> None:
        # Ставим флаг остановки и запускаем анимацию
        self.is_stopping_session = True
        
        # Останавливаем предыдущую анимацию, если была, и запускаем новую
        # Это исправляет баг, когда при нажатии STOP показывался CONNECT вместо DISCONNECT
        if self.loading_timer.isActive():
            self.loading_timer.stop()
        
        # Принудительно устанавливаем состояние отключения
        self.is_connecting_strategy = False
        self.start_loading_base_text = self._tr("DISCONNECT")
        self.start_loading_animation(connecting=False)
            
        # Очищаем инфо-статус при остановке сессии
        self.info_status_label.setText("")
            
        try:
            if stop_service:
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

            # Отключаем WARP при остановке стратегии (полная деактивация)
            try:
                success, msg = warp.disconnect_warp()
                if success:
                    logger.info("WARP deactivated on strategy stop")
                    self.warp_is_connected = False
                    self.warp_is_registered = False
                else:
                    logger.warning(f"WARP deactivation on stop message: {msg}")
            except Exception as e:
                logger.debug(f"WARP deactivation error on strategy stop: {e}")

            self.show_status(self._tr("Stopped"), "#107C10")
        except Exception as e:
            logger.error(f"Stop error: {e}")
            self.show_status(self._tr("Stop error"), "#ff6b6b")
        finally:
            self.stop_loading_animation(False)
            # После остановки стратегии даём короткий кулдаун на кнопку START/STOP.
            self._start_start_cooldown()
            self.update_warp_button_style()
    
    def _show_centered_password_dialog(self) -> tuple[str, bool]:
        """Show password input dialog centered on main window. Same on X11 and Wayland."""
        dialog = QDialog(self)
        dialog.setWindowTitle(self._tr("Authorization"))
        dialog.setModal(True)
        layout = QFormLayout(dialog)
        line_edit = QLineEdit()
        line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        line_edit.setPlaceholderText(self._tr("Enter sudo password:"))
        
        # Invoke Steam keyboard on click
        def on_clicked(event):
            webbrowser.open("steam://open/keyboard")
            QLineEdit.mousePressEvent(line_edit, event)
        line_edit.mousePressEvent = on_clicked
        
        layout.addRow(self._tr("Enter sudo password:"), line_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        dialog.resize(400, 120)
        dialog.adjustSize()
        # Center dialog on main window (same on X11 and Wayland)
        mw_rect = self.frameGeometry()
        cx = mw_rect.x() + mw_rect.width() // 2
        cy = mw_rect.y() + mw_rect.height() // 2
        dialog.move(cx - dialog.width() // 2, cy - dialog.height() // 2 - 40)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return (line_edit.text().strip(), True)
        return ("", False)

    def ask_sudo_password(self) -> Optional[str]:
        if self.sudo_password:
            return self.sudo_password
        if self._password_prompt_in_progress:
            return None

        self._password_prompt_in_progress = True
        try:
            return self._do_ask_sudo_password()
        finally:
            self._password_prompt_in_progress = False

    def _do_ask_sudo_password(self) -> Optional[str]:
        # Unified centered password dialog for both X11 and Wayland
        text, ok = self._show_centered_password_dialog()
        if not ok:
            text = ""
        
        if text:
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
        """
        Показать упрощённый статус снизу.

        Вместо длинных фраз отображаем только одно слово,
        а подробности оставляем в логах.

        Локализация:
        - ru:  ГОТОВО / ЖДИТЕ / ОШИБКА
        - иное: READY / WAIT / ERROR
        """
        c = color.lower()
        lang = QLocale.system().language()

        if "#ef4444" in c or "#ff6b6b" in c:
            code = "ERROR"
        elif "#f59e0b" in c or "#ff8c00" in c:
            code = "WAIT"
        else:
            code = "READY"

        if lang == QLocale.Language.Russian:
            mapping = {
                "READY": "ГОТОВО",
                "WAIT": "ЖДИТЕ",
                "ERROR": "ОШИБКА",
            }
        else:
            mapping = {
                "READY": "READY",
                "WAIT": "WAIT",
                "ERROR": "ERROR",
            }

        simplified = mapping.get(code, code)

        grad = _GRAD_RED if code == "ERROR" else \
               _GRAD_ORANGE if code == "WAIT" else \
               _GRAD_GREEN
        
        self.status_label.setText(simplified)
        self.status_label.setStyleSheet(
            f"color: {grad}; background: transparent; font-weight: bold; font-size: 14px;"
        )
    
    def toggle_service_tile(self) -> None:
        # Не позволяем переключать сервис, пока идёт запуск/остановка
        # стратегий, автоподбор или операция WARP / cooldown.
        if self.loading_timer.isActive() or self.is_auto_discovering or self.is_changing_warp or self.warp_cooldown_active:
            return
        password = self.ask_sudo_password()
        if not password:
            return
        
        self.is_changing_service = True
        self.service_btn.setEnabled(False)
        self.show_status(self._tr("Checking service status..."), "#FF8C00")
        
        try:
            currently_running = is_service_running()
            target_state = not currently_running
            action = "install" if target_state else "remove"
            
            self.show_status(
                self._tr("Enabling background mode...") if target_state
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
                self.show_status(
                    self._tr("Service error: {error}").format(error=error_msg or self._tr("command failed")),
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
                    time.sleep(1)
                else:
                    self.show_status(self._tr("Service failed to start!"), "#ff6b6b")
                    self.service_btn.setEnabled(True)
                    self.is_changing_service = False
                    return
            
            self.service_btn.blockSignals(True)
            self.service_btn.setChecked(target_state)
            self.service_btn.blockSignals(False)
            self.show_status(
                self._tr("Background service enabled") if target_state
                else self._tr("Background service disabled"),
                "#107C10"
            )
        except Exception as e:
            logger.error(f"Service toggle exception: {e}")
            self.show_status(self._tr("Critical service error"), "#ff6b6b")
        finally:
            self.service_btn.setEnabled(True)
            # Сбрасываем флаг с задержкой, чтобы сервис успел стабилизироваться
            QTimer.singleShot(3000, lambda: setattr(self, 'is_changing_service', False))
    
    def toggle_game_filter_tile(self) -> None:
        # Не позволяем менять фильтр, пока выполняются тяжёлые операции.
        if self.loading_timer.isActive() or self.is_auto_discovering or self.is_changing_warp or self.warp_cooldown_active:
            return
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
                    self._tr("Game filter enabled") if state
                    else self._tr("Game filter disabled"),
                    "#107C10"
                )
        else:
            self.game_filter_btn.blockSignals(True)
            self.game_filter_btn.setChecked(not state)
            self.game_filter_btn.blockSignals(False)
    
    def on_strategy_changed(self, text: str) -> None:
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
        # Set flag to ignore session changes during service restart
        self.is_changing_service = True
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
            self.show_status(self._tr("Failed to apply setting"), "#ff6b6b")
        finally:
            # Reset flag after a short delay to allow the service to stabilize
            QTimer.singleShot(2000, lambda: setattr(self, 'is_changing_service', False))
    
    def on_service_changed(self, state: bool) -> None:
        if getattr(self, 'is_changing_service', False):
            return
        if self.service_btn.isChecked() != state:
            self.service_btn.blockSignals(True)
            self.service_btn.setChecked(state)
            self.service_btn.blockSignals(False)
    
    def create_labeled_combo(self, label: str, items: list, current: str) -> QFrame:
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
    
    def start_log_monitor(self) -> None:
        """Start log monitoring thread."""
        log_file = os.path.join(BASE_DIR, "debug.log")
        self.log_monitor = LogMonitor(log_file)
        self.log_monitor.info_status_found.connect(self.on_info_status_found)
        self.log_monitor.start()
    
    def on_info_status_found(self, status_text: str) -> None:
        """Handle INFO status found in log file."""
        # Ignore signals during initial sync
        if not self._initial_sync_done:
            return
        
        # Show info status only while loading/starting session (before WARP START appears)
        # This means: show status when is_starting_session is True and WARP is not yet connected
        if self.is_starting_session and not self.warp_is_connected:
            self.info_status_label.setText(status_text)
            # Обновляем кнопку WARP чтобы показать лог в реальном времени
            self.update_warp_button_style()
        elif self.is_stopping_session or not self.is_starting_session:
            # Clear info status when stopping or after session stopped
            self.info_status_label.setText("")
            # Обновляем кнопку WARP чтобы вернуть обычный текст
            self.update_warp_button_style()

    def start_status_checker(self) -> None:
        self.checker = StatusChecker()
        self.checker.session_changed.connect(self.on_session_changed)
        self.checker.service_changed.connect(self.on_service_changed)
        self.checker.warp_status_changed.connect(self.on_warp_status_changed)
        self.checker.warp_registration_changed.connect(self.on_warp_registration_changed)
        self.checker.start()
        QTimer.singleShot(300, self.load_strategies)
    
    def on_warp_status_changed(self, is_connected: bool) -> None:
        """Handle WARP status change signal from background thread."""
        # Ignore signals during initial sync
        if not self._initial_sync_done:
            return
        
        # Don't update status while WARP operation is in progress or cooldown
        if self.is_changing_warp or self.warp_cooldown_active:
            return
        
        if is_connected != self.warp_is_connected:
            # Protection against false "Disconnected" shortly after "Connected"
            if self.warp_is_connected and not is_connected and self._warp_connect_success_at is not None:
                if time.time() - self._warp_connect_success_at < 12:
                    return

            logger.info(f"WARP status changed (via bg signal): {is_connected}")
            self.warp_is_connected = is_connected
            self.update_warp_button_style()

    def on_warp_registration_changed(self, is_registered: bool) -> None:
        """Handle WARP registration status change signal from background thread."""
        # Ignore signals during initial sync
        if not self._initial_sync_done:
            return
        
        if not self.warp_installed:
            return

        # Don't update during active operations
        if self.is_changing_warp or self.warp_cooldown_active or self.is_registering_warp:
            return

        if is_registered != self.warp_is_registered:
            logger.info(f"WARP registration status changed (via bg signal): {is_registered}")
            self.warp_is_registered = is_registered
            self.update_warp_button_style()

        # Trigger background registration if needed
        if self.is_running and not is_registered and not self.is_registering_warp:
            self._bg_reg_count = getattr(self, '_bg_reg_count', 0) + 1
            if self._bg_reg_count <= 3:
                 logger.info(f"Starting background registration (attempt {self._bg_reg_count})...")
                 self.start_background_warp_registration()

    def start_background_warp_registration(self) -> None:
        """Start WARP registration in a background thread."""
        if self.is_registering_warp:
            return
            
        self.is_registering_warp = True
        sudo_password = self.sudo_password
        
        def registration_task():
            try:
                # Use a small number of retries (2) instead of infinite (-1)
                # to prevent Cloudflare GUI from popping up repeatedly.
                success, msg = warp.register_warp_with_verification(max_retries=2, sudo_password=sudo_password)
                logger.info(f"Background WARP registration result: {success}, {msg}")
            except Exception as e:
                logger.error(f"Background WARP registration error: {e}")
            finally:
                self.is_registering_warp = False
                # Background monitoring eventually updates UI, 
                # but we trigger immediate UI update here for better responsiveness.
                if success:
                    QTimer.singleShot(0, lambda: self.on_warp_registration_changed(True))

        threading.Thread(target=registration_task, daemon=True).start()
    
    def on_session_changed(self, running: bool) -> None:
        """Handle session state changes from StatusChecker."""
        # Ignore signals during initial sync
        if not self._initial_sync_done:
            return
        
        # Ignore signals during service toggle operations
        if self.is_changing_service:
            return
        
        previous_running = self.is_running
        self.is_running = running

        if self.is_auto_discovering:
            return
        
        # 🚫 Во время анимации - ТОЛЬКО берем ожидаемое состояние, все остальное игнорируем
        if self.loading_timer.isActive():
            # Если ожидаем запуск (is_starting_session=True)
            if self.is_starting_session:
                if not running:
                    # Дребезг - игнорируем
                    logger.debug(f"Ignoring debounce during start animation (running={running})")
                    return
                # Ожидаемое состояние (running=True) - обновляем UI
                logger.debug(f"Received expected state during start animation (running={running})")
                self.is_starting_session = False
                QTimer.singleShot(0, lambda: self._update_session_ui(running, previous_running))
                return
        
            # Если ожидаем остановку (is_stopping_session=True)
            if self.is_stopping_session:
                if running:
                    # Дребезг - игнорируем
                    logger.debug(f"Ignoring debounce during stop animation (running={running})")
                    return
                # Ожидаемое состояние (running=False) - обновляем UI
                logger.debug(f"Received expected state during stop animation (running={running})")
                self.is_stopping_session = False
                QTimer.singleShot(0, lambda: self._update_session_ui(running, previous_running))
                return
            
            # Таймер активен но флаги не установлены - это может быть дребезг
            # Игнорируем обновление, чтобы не сбивать анимацию
            logger.debug(f"Session changed during animation but no transition flags (running={running}) - ignoring")
            return

        # 🚫 Если мы только что завершили переходное состояние, блокируем дребезг на 5 sec
        if time.time() < self._transition_lock_until:
            # Но если состояние совпадает с заблокированным - пропускаем блокировку
            if running != self._locked_state:
                logger.debug(f"Ignoring state change during lock (running={running}, locked={self._locked_state})")
                return
        
        # Проверяем - действительно ли состояние изменилось?
        if running == self.is_running and not (self.is_starting_session or self.is_stopping_session):
            return

        # Обновляем UI
        QTimer.singleShot(0, lambda: self._update_session_ui(running, previous_running))

    def _update_session_ui(self, running: bool, previous_running: bool) -> None:
        """Update session UI in main thread."""
        # Блокировка обновления UI во время изменения сервиса
        if self.is_changing_service:
            logger.debug(f"Ignoring session UI update during service change")
            return

        # ✅ Сбрасываем флаги ТОЛЬКО если они совпадают с текущим состоянием
        should_update = False

        if self.is_starting_session and running:
            self.is_starting_session = False
            should_update = True
            logger.debug(f"Session started successfully (running=True)")

        if self.is_stopping_session and not running:
            self.is_stopping_session = False
            should_update = True
            logger.debug(f"Session stopped successfully (running=False)")
        
        # Если ни один флаг не был сброшен, это нормальный сигнал (не переходное состояние)
        if not should_update and (self.is_starting_session or self.is_stopping_session):
            # Флаг установлен но состояние не совпадает - это дребезг, игнорируем
            logger.debug(f"Ignoring UI update during transition (starting={self.is_starting_session}, stopping={self.is_stopping_session})")
            return

        # ✅ Если переходное состояние только что завершилось, блокируем обновления на 5 сек
        if should_update:
            self._locked_state = running
            self._transition_lock_until = time.time() + 5.0
            logger.debug(f"Transition completed, locking {('running=True' if running else 'running=False')} for 5 seconds")

        # ✅ Остановить анимацию только если завершено переходное состояние
        # Не останавливаем анимацию если is_starting_session или is_stopping_session всё ещё True
        if self.loading_timer.isActive() and should_update:
            self.loading_timer.stop()
        
        # Сбрасываем задержку и состояние подключения только если переход завершён
        if should_update:
            self.is_start_loading_delayed = False
            self.is_connecting_strategy = None
            self.start_btn.setEnabled(True)
            
            # ✅ Явно установить кнопку в правильное состояние БЕЗ других проверок
            text = self._tr("STOP") if running else self._tr("START")
            grad = _GRAD_RED if running else _GRAD_GREEN
            self.start_btn.setText(text)
            self.start_btn.setStyleSheet(f"color:#fff; background:{grad}; {_BTN_STYLE_BASE}")

        # Если стратегия остановлена, останавливаем анимацию WARP и отключаем сам WARP (строгое правило)
        if not running:
            self.stop_warp_loading_animation()
            if self.warp_is_connected:
                logger.info("Strategy stopped while WARP was connected. Deactivating WARP...")
                def _full_deactivate():
                    success, msg = warp.disconnect_warp()
                    if success:
                        self.warp_is_connected = False
                        self.warp_is_registered = False
                        QTimer.singleShot(0, self.update_warp_button_style)
                
                threading.Thread(target=_full_deactivate, daemon=True).start()

        self.update_warp_button_style()

        # Регистрация WARP строго в фоне после подключения к любой стратегии
        if not previous_running and running and self.warp_installed and not self.warp_is_registered and not self.is_registering_warp:
            # Запускаем анимацию регистрации
            self._warp_reg_animation_active = True
            self._start_warp_registration_animation()
            self.start_background_warp_registration()

        # Короткий кулдаун после успешного старта сессии,
        # чтобы защититься от двойных нажатий.
        if not previous_running and running:
            self._start_start_cooldown()
    
    def show_msg(self, title: str, text: str) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.addButton(self._tr("OK"), QMessageBox.ButtonRole.AcceptRole)
        # Center and move 40px higher
        msg.show()
        msg_rect = msg.frameGeometry()
        parent_rect = self.frameGeometry()
        cx = parent_rect.x() + parent_rect.width() // 2
        cy = parent_rect.y() + parent_rect.height() // 2
        msg.move(cx - msg_rect.width() // 2, cy - msg_rect.height() // 2 - 40)
        msg.exec()
    
    def load_config(self) -> None:
        self.saved_strategy = self.config.load_strategy()
        self.game_filter_enabled = self.config.load_game_filter()
        self.load_strategies()
        self.game_filter_btn.setChecked(self.game_filter_enabled)
    
    def load_strategies(self) -> None:
        all_strategies = load_strategies()
        display_strategies = [s for s in all_strategies if s != "auto_found.bat"]

        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        self.strategy_combo.addItem(self._tr("Auto-discovery"))
        self.strategy_combo.addItems(display_strategies)

        if self.saved_strategy == "auto_found.bat":
            self.strategy_combo.setCurrentText(self._tr("Auto-discovery"))
        elif self.saved_strategy in display_strategies:
            self.strategy_combo.setCurrentText(self.saved_strategy)
        else:
            self.strategy_combo.setCurrentIndex(0)
        self.strategy_combo.blockSignals(False)

        self.start_btn.setEnabled(True)
    
    def check_for_update(self) -> None:
        try:
            self.update_checker = UpdateChecker(CURRENT_VERSION, check_prerelease="DEVEL" in CURRENT_VERSION)
            self.update_checker.update_available.connect(self.on_update_available)
            self.update_checker.start()
        except Exception as e:
            logger.debug(f"Update check failed to start: {e}")

    def on_update_available(self, version: str, download_url: str) -> None:
        self.update_label.setText(
            self._tr("Available: v{version}").format(version=version)
        )
        self.version_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #ef4444;")
        
        msg = QMessageBox(self)
        msg.setWindowTitle(self._tr("Update"))
        msg.setText(self._tr("Доступна новая версия, обновить?"))
        yes_btn = msg.addButton(self._tr("Yes"), QMessageBox.ButtonRole.YesRole)
        no_btn = msg.addButton(self._tr("No"), QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(yes_btn)
        
        # Center and move 40px higher
        msg.show()
        msg_rect = msg.frameGeometry()
        parent_rect = self.frameGeometry()
        cx = parent_rect.x() + parent_rect.width() // 2
        cy = parent_rect.y() + parent_rect.height() // 2
        msg.move(cx - msg_rect.width() // 2, cy - msg_rect.height() // 2 - 40)
        
        msg.exec()
        if msg.clickedButton() == yes_btn:
            self.perform_update(download_url)
            
    def perform_update(self, download_url: str) -> None:
        if self.is_running:
            password = self.ask_sudo_password()
            if password:
                self.stop_session(password, stop_service=True)
        self.show_status(self._tr("Starting update..."), "#FF8C00")
        self.updater_worker = UpdaterWorker(download_url)
        self.updater_worker.update_finished.connect(self.on_update_finished)
        self.updater_worker.start()

    def on_update_finished(self, success: bool, message: str) -> None:
        if success:
            QApplication.quit()
        else:
            self.show_msg(self._tr("Update error"), self._tr(message))
    
    def closeEvent(self, event) -> None:
        """Handle window close event."""
        logger.info("Closing application")

        # Cleanup WARP if it was activated by this application
        try:
            warp._cleanup_warp()
        except Exception as e:
            logger.error(f"Error during WARP cleanup on close: {e}")

        self.loading_timer.stop()
        self.warp_timer.stop()
        self.is_changing_warp = False

        if hasattr(self, 'warp_status_timer'):
            self.warp_status_timer.stop()
        
        if hasattr(self, 'warp_registration_timer'):
            self.warp_registration_timer.stop()

        if hasattr(self, 'checker'):
            self.checker.stop()
            self.checker.wait()

        if hasattr(self, 'log_monitor'):
            self.log_monitor.stop()
            self.log_monitor.wait()

        event.accept()
