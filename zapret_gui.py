#!/usr/bin/env python3
import os
import subprocess
import sys
import logging
import shutil
import webbrowser
import threading
from packaging import version
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFrame, QMessageBox,
    QInputDialog, QLineEdit, QGridLayout, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QCursor

# === ПУТИ ===
if os.path.exists("/opt/zapretdeck") and os.path.isfile("/opt/zapretdeck/zapret_gui.py"):
    BASE_DIR = "/opt/zapretdeck"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CUSTOM_STRATEGIES_DIR = os.path.join(BASE_DIR, "custom-strategies")
LATEST_STRATEGIES_DIR = os.path.join(BASE_DIR, "zapret-latest")
CONF_FILE = os.path.join(BASE_DIR, "conf.env")
MAIN_SCRIPT = os.path.join(BASE_DIR, "main_script.sh")
STOP_SCRIPT = os.path.join(BASE_DIR, "stop_and_clean_nft.sh")
RENAME_SCRIPT = os.path.join(BASE_DIR, "rename_bat.sh")
SERVICE_SCRIPT = os.path.join(BASE_DIR, "service.sh")
LOG_FILE = os.path.join(BASE_DIR, "debug.log")
ICON_PATH = os.path.join(BASE_DIR, "zapretdeck.png")

print(f"[ZapretDeck] Базовая директория: {BASE_DIR}")

# === ЛОГИ ===
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    filemode='a'
)
logger = logging.getLogger(__name__)

HIDDEN_STRATEGIES = {"check_updates.bat", "service_install.bat", "service_remove.bat", "service_status.bat"}
CURRENT_VERSION = "0.1.5"


# === МОНИТОРИНГ ===
class StatusChecker(QThread):
    session_changed = pyqtSignal(bool)
    service_changed = pyqtSignal(bool)

    def run(self):
        while True:
            try:
                running = subprocess.run(["pgrep", "-f", "nfqws"], capture_output=True).returncode == 0
                self.session_changed.emit(running)

                enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", "zapretdeck.service"], check=False).returncode == 0
                active = subprocess.run(["systemctl", "is-active", "--quiet", "zapretdeck.service"], check=False).returncode == 0
                self.service_changed.emit(enabled and active)

                QThread.msleep(1500)
            except Exception as e:
                logger.error(f"StatusChecker error: {e}")
                QThread.msleep(2000)


# === GUI ===
class ZapretGUI(QMainWindow):
    status_requested = pyqtSignal(str, str)
    auto_discovery_done = pyqtSignal(str)
    set_button_busy = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZapretDeck")
        self.setMinimumSize(800, 600)
        self.showMaximized()

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.sudo_password = None
        self.saved_strategy = ""
        self.game_filter_enabled = False
        self.is_running = False
        self.is_changing_service = False
        self.is_auto_discovering = False
        self.loading_dots = 0
        self.loading_timer = QTimer()
        self.loading_timer.timeout.connect(self.update_loading_animation)

        if not self.check_dependencies():
            self.show_msg("Ошибка", "Отсутствуют зависимости! Установите: ip, nft, systemctl, pgrep, pkill, nmcli, curl")
            sys.exit(1)

        self.init_ui()
        self.load_config()
        self.start_status_checker()
        QTimer.singleShot(1000, self.check_for_update)

        QTimer.singleShot(2000, self.sync_service_button_on_startup)

        self.status_requested.connect(self.show_status)
        self.auto_discovery_done.connect(self.on_auto_success)
        self.set_button_busy.connect(self.update_button_loading_state)

        self.show_status("Готов к работе!", "#107C10")

    def sync_service_button_on_startup(self):
        try:
            enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", "zapretdeck.service"], check=False).returncode == 0
            active = subprocess.run(["systemctl", "is-active", "--quiet", "zapretdeck.service"], check=False).returncode == 0
            real_state = enabled and active

            if self.service_btn.isChecked() != real_state:
                logger.info(f"Синхронизация кнопки 'Работа в фоне': было {'включено' if self.service_btn.isChecked() else 'выключено'} → стало {'включено' if real_state else 'выключено'}")
                self.service_btn.blockSignals(True)
                self.service_btn.setChecked(real_state)
                self.service_btn.blockSignals(False)
            else:
                logger.info(f"Кнопка 'Работа в фоне' уже в правильном состоянии: {'включено' if real_state else 'выключено'}")
        except Exception as e:
            logger.error(f"Ошибка синхронизации кнопки сервиса при запуске: {e}")

    def update_button_loading_state(self, is_busy):
        if is_busy:
            self.start_btn.setEnabled(False)
            self.start_btn.setText("ИДЁТ АВТОПОДБОР...")
            self.start_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #FF8C00, stop:1 #FF4500);
                    color: white; 
                    font-weight: bold;
                    font-size: 20px;
                    border-radius: 12px;
                    border: none;
                }
            """)
        else:
            self.start_btn.setEnabled(True)
            self.start_btn.setStyleSheet("")
            self.apply_session_style(self.is_running)

    def on_auto_success(self, filename):
        self.set_button_busy.emit(False)
        
        if os.path.exists(os.path.join(CUSTOM_STRATEGIES_DIR, filename)):
            self.strategy_combo.setCurrentText(filename)
        self.run_main_script(self.sudo_password)

    def init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        scroll.setWidget(container)
        self.setCentralWidget(scroll)

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
        self.version_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #107C10;")
        top_layout.addWidget(self.version_label)

        combo_frame = self.create_labeled_combo("Текущий обход блокировок:", [], "")
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

        self.service_btn = QPushButton("Работа в фоне")
        self.service_btn.setCheckable(True)
        self.service_btn.setStyleSheet(tile_style)
        self.service_btn.clicked.connect(self.toggle_service_tile)

        self.game_filter_btn = QPushButton("Игровой фильтр")
        self.game_filter_btn.setCheckable(True)
        self.game_filter_btn.setStyleSheet(tile_style)
        self.game_filter_btn.clicked.connect(self.toggle_game_filter_tile)

        tiles_layout.addWidget(self.service_btn, 1)
        tiles_layout.addWidget(self.game_filter_btn, 1)

        layout.addWidget(tiles_frame)

        self.start_btn = QPushButton("ПУСК")
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
            ("ВКонтакте", "https://vk.com/valvesteamdeck"),
            ("Telegram", "https://t.me/deckru"),
            ("Поддержать автора", "https://vk.com/valvesteamdeck?w=donut_payment-199643211&levelId=1669"),
            ("MAX", "https://max.ru/valvesteamdeck"),
        ]
        for i, (text, url) in enumerate(actions):
            btn = QPushButton(text)
            btn.setObjectName("actionButton")
            btn.setMinimumHeight(44)
            btn.clicked.connect(lambda _, u=url: webbrowser.open(u))
            actions_layout.addWidget(btn, i // 2, i % 2)

        layout.addWidget(actions_card)

        exit_btn = QPushButton("Выход")
        exit_btn.setObjectName("exitButton")
        exit_btn.setMinimumHeight(56)
        exit_btn.clicked.connect(self.close)
        layout.addWidget(exit_btn)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px;")
        self.status_label.setMinimumHeight(30)
        layout.addWidget(self.status_label)

        self.update_label = QLabel("")
        self.update_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_label.setStyleSheet("color: #ff6b6b; font-weight: bold; font-size: 14px;")
        self.update_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.update_label.mousePressEvent = lambda e: webbrowser.open("https://github.com/rosakodu/zapretdeck/releases/latest")
        self.update_label.setMinimumHeight(30)
        layout.addWidget(self.update_label)

        layout.addStretch()

    def apply_session_style(self, running):
        if self.loading_timer.isActive() or getattr(self, 'is_auto_discovering', False):
            return
        text = "СТОП" if running else "ПУСК"
        grad = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #E53935,stop:1 #B71C1C)" if running else "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4CAF50,stop:1 #2E7D32)"
        self.start_btn.setText(text)
        self.start_btn.setStyleSheet(f"color:#fff; background:{grad}; border-radius:12px; font-weight:bold; font-size:20px;")

    def start_loading_animation(self, action: str):
        self.loading_dots = 0
        base = "ЗАПУСК" if action == "start" else "ОСТАНОВКА"
        self.start_btn.setText(f"{base}...")
        self.start_btn.setEnabled(False)
        self.loading_timer.start(500)

    def update_loading_animation(self):
        self.loading_dots = (self.loading_dots + 1) % 4
        dots = "." * self.loading_dots
        current = self.start_btn.text().rstrip(".")
        self.start_btn.setText(f"{current}{dots}")

    def stop_loading_animation(self):
        self.loading_timer.stop()
        self.start_btn.setEnabled(True)
        self.apply_session_style(self.is_running)

    def start_zapret(self):
        if self.loading_timer.isActive():
            return

        try:
            enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", "zapretdeck.service"], check=False).returncode == 0
            active = subprocess.run(["systemctl", "is-active", "--quiet", "zapretdeck.service"], check=False).returncode == 0
            service_running = enabled and active
        except:
            service_running = False

        if service_running:
            self.show_status("Уже работает в фоне!", "#107C10")
            return

        password = self.ask_sudo_password()
        if not password:
            return

        current_strat = self.strategy_combo.currentText()

        if self.is_running:
            self.start_loading_animation("stop")
            QTimer.singleShot(100, lambda: self.stop_session(password))
            return

        if not current_strat:
            self.show_status("Выбери стратегию!", "#ff6b6b")
            return

        if current_strat == "Автоподбор":
            threading.Thread(target=self.run_auto_discovery, args=(password,), daemon=True).start()
        else:
            self.run_main_script(password)

    def run_auto_discovery(self, password):
        self.is_auto_discovering = True
        self.set_button_busy.emit(True)
        self.status_requested.emit("Подбор стратегии... (ждите)", "#FF8C00")

        try:
            result = subprocess.run(
                ["sudo", "-S", "bash", MAIN_SCRIPT, "auto"],
                input=password + "\n",
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.status_requested.emit("Стратегия подобрана!", "#107C10")
                self.auto_discovery_done.emit("auto_found.bat")
            else:
                self.status_requested.emit("Автоподбор не удался", "#ff6b6b")
                
        except Exception as e:
            logger.error(f"Ошибка при автоподборе: {e}")
            self.status_requested.emit(f"Ошибка: {str(e)}", "#ff6b6b")
        
        finally:
            self.is_auto_discovering = False
            self.set_button_busy.emit(False)

    def on_session_changed(self, running):
        self.is_running = running
        if getattr(self, 'is_auto_discovering', False):
            return
            
        self.stop_loading_animation()
        self.apply_session_style(running)

    def run_main_script(self, password):
        try:
            subprocess.run(
                ["sudo", "-S", "bash", STOP_SCRIPT],
                input=password + "\n", text=True, check=False, timeout=10
            )
        except:
            pass

        self.update_config("silent")
        self.start_loading_animation("start")

        try:
            proc = subprocess.Popen(
                ["sudo", "-S", "bash", MAIN_SCRIPT],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True
            )
            proc.stdin.write(password + "\n")
            proc.stdin.flush()
        except Exception as e:
            logger.error(f"Ошибка запуска main_script: {e}")
            self.show_status("Ошибка запуска", "#ff6b6b")
            self.stop_loading_animation()

    def stop_session(self, password):
        try:
            subprocess.run(
                ["sudo", "-S", "bash", STOP_SCRIPT],
                input=password + "\n", text=True, check=True, timeout=15
            )
            self.show_status("Остановлено", "#107C10")
        except Exception as e:
            logger.error(f"Stop error: {e}")
            self.show_status("Ошибка остановки", "#ff6b6b")
        finally:
            self.stop_loading_animation()

    def ask_sudo_password(self):
        if self.sudo_password:
            return self.sudo_password

        text, ok = QInputDialog.getText(
            self, "Авторизация", "Введите пароль sudo:",
            QLineEdit.EchoMode.Password
        )

        if ok and text:
            res = subprocess.run(["sudo", "-S", "true"], input=text + "\n", text=True, capture_output=True)
            if res.returncode == 0:
                self.sudo_password = text
                return text
            else:
                self.show_status("Неверный пароль", "#ff6b6b")
        return None

    def show_status(self, text, color="#107C10"):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 14px;")

    def toggle_service_tile(self):
        password = self.ask_sudo_password()
        if not password:
            return

        self.is_changing_service = True
        self.service_btn.setEnabled(False)
        self.show_status("Проверка состояния сервиса...", "#FF8C00")

        try:
            enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", "zapretdeck.service"], check=False).returncode == 0
            active = subprocess.run(["systemctl", "is-active", "--quiet", "zapretdeck.service"], check=False).returncode == 0
            currently_running = enabled and active

            target_state = not currently_running
            action = "install" if target_state else "remove"

            self.show_status(f"{'Включение' if target_state else 'Выключение'} фонового режима...", "#FF8C00")

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
                self.show_status(f"Ошибка сервиса: {error_msg or 'команда не удалась'}", "#ff6b6b")
                self.service_btn.setEnabled(True)
                self.is_changing_service = False
                return

            if target_state:
                self.show_status("Запуск сервиса...", "#FF8C00")
                for _ in range(15):
                    status_check = subprocess.run(
                        ["systemctl", "is-active", "--quiet", "zapretdeck.service"],
                        timeout=5
                    )
                    if status_check.returncode == 0:
                        break
                    QThread.msleep(1000)
                else:
                    self.show_status("Сервис не запустился!", "#ff6b6b")
                    self.service_btn.setEnabled(True)
                    self.is_changing_service = False
                    return

            self.service_btn.blockSignals(True)
            self.service_btn.setChecked(target_state)
            self.service_btn.blockSignals(False)
            self.show_status("Работа в фоне включена" if target_state else "Работа в фоне отключена", "#107C10")

        except Exception as e:
            logger.error(f"Service toggle exception: {e}")
            self.show_status("Критическая ошибка сервиса", "#ff6b6b")

        finally:
            self.service_btn.setEnabled(True)
            self.is_changing_service = False

    def toggle_game_filter_tile(self):
        state = self.game_filter_btn.isChecked()
        password = self.ask_sudo_password()
        if password:
            old_state = self.game_filter_enabled
            self.game_filter_enabled = state
            self.update_config()

            if old_state != state and self.service_btn.isChecked():
                # Автоматический перезапуск фона при смене фильтра
                self.show_status("Применяю новый фильтр (перезапуск фона)...", "#FF8C00")
                QTimer.singleShot(500, self.restart_background_service_silent)
            else:
                self.show_status(f"Игровой фильтр {'включён' if state else 'выключен'}", "#107C10")
        else:
            self.game_filter_btn.blockSignals(True)
            self.game_filter_btn.setChecked(not state)
            self.game_filter_btn.blockSignals(False)

    def on_strategy_changed(self, text):
        if not text:
            return

        password = self.ask_sudo_password()
        if not password:
            self.strategy_combo.blockSignals(True)
            self.strategy_combo.setCurrentText(self.saved_strategy)
            self.strategy_combo.blockSignals(False)
            return

        old_strategy = self.saved_strategy
        self.saved_strategy = "auto_found.bat" if text == "Автоподбор" else text

        if old_strategy != self.saved_strategy:
            self.update_config()
            self.show_status("Стратегия сохранена", "#107C10")

            if self.service_btn.isChecked():
                # Автоматический перезапуск фона при смене стратегии
                self.show_status("Применяю новую стратегию (перезапуск фона)...", "#FF8C00")
                QTimer.singleShot(500, self.restart_background_service_silent)
        else:
            self.show_status("Стратегия сохранена", "#107C10")

    def restart_background_service_silent(self):
        """Тихий перезапуск сервиса (без запроса пароля и сообщений)"""
        try:
            subprocess.run(["sudo", "systemctl", "restart", "zapretdeck.service"], check=True, timeout=30)
            QTimer.singleShot(1000, lambda: self.show_status("Новая настройка применена", "#107C10"))
        except Exception as e:
            logger.error(f"Тихий перезапуск сервиса не удался: {e}")
            self.show_status("Не удалось применить настройку", "#ff6b6b")

    def on_service_changed(self, state):
        if getattr(self, 'is_changing_service', False):
            return
        if self.service_btn.isChecked() != state:
            self.service_btn.blockSignals(True)
            self.service_btn.setChecked(state)
            self.service_btn.blockSignals(False)

    def create_labeled_combo(self, label, items, current):
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

    def start_status_checker(self):
        self.checker = StatusChecker()
        self.checker.session_changed.connect(self.on_session_changed)
        self.checker.service_changed.connect(self.on_service_changed)
        self.checker.start()
        QTimer.singleShot(300, self.load_strategies)

    def show_msg(self, title, text):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.addButton("ОК", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Отменить", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

    def update_config(self, source=None):
        try:
            current_strat = self.strategy_combo.currentText()
            strat_to_save = "auto_found.bat" if current_strat == "Автоподбор" else current_strat
            self.saved_strategy = strat_to_save

            with open(CONF_FILE, "w") as f:
                f.write(f"interface=any\n")
                f.write(f"strategy={strat_to_save}\n")
                f.write(f"gamefilter={'true' if self.game_filter_enabled else 'false'}\n")
                f.write(f"auto_update=false\n")

            if source != "silent":
                self.show_status("Настройки сохранены", "#107C10")
            logger.info(f"Конфиг обновлен: стратегия={strat_to_save}")
        except Exception as e:
            logger.error(f"Ошибка update_config: {e}")
            self.show_status("Ошибка сохранения конфига", "#ff6b6b")

    def load_config(self):
        if os.path.exists(CONF_FILE):
            with open(CONF_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("strategy="):
                        self.saved_strategy = line.split("=", 1)[1]
                    elif line.startswith("gamefilter="):
                        val = line.split("=", 1)[1].lower()
                        self.game_filter_enabled = val in ("true", "1", "yes", "on", "enabled")
        self.load_strategies()
        self.game_filter_btn.setChecked(self.game_filter_enabled)

    def check_dependencies(self):
        deps = ['ip', 'nft', 'systemctl', 'pgrep', 'pkill', 'bash', 'nmcli', 'curl']
        return all(shutil.which(d) for d in deps)

    def load_strategies(self):
        strategies = []

        if os.path.exists(CUSTOM_STRATEGIES_DIR):
            try:
                custom_strategies = [f for f in os.listdir(CUSTOM_STRATEGIES_DIR)
                                     if f.endswith(".bat") and f not in HIDDEN_STRATEGIES]
                strategies.extend(custom_strategies)
            except Exception as e:
                logger.error(f"Ошибка чтения custom-strategies: {e}")

        if os.path.exists(LATEST_STRATEGIES_DIR):
            try:
                latest_strategies = [f for f in os.listdir(LATEST_STRATEGIES_DIR)
                                     if f.endswith(".bat") and f not in HIDDEN_STRATEGIES]
                strategies.extend(latest_strategies)
            except Exception as e:
                logger.error(f"Ошибка чтения zapret-latest: {e}")

        if os.path.exists(CUSTOM_STRATEGIES_DIR) and any(f.endswith(".bat") for f in os.listdir(CUSTOM_STRATEGIES_DIR)):
            if os.path.exists(RENAME_SCRIPT):
                try:
                    subprocess.run(["bash", RENAME_SCRIPT], cwd=BASE_DIR, capture_output=True)
                    logger.info("rename_bat.sh применён к custom-strategies")
                except Exception as e:
                    logger.error(f"Ошибка запуска rename_bat.sh: {e}")

        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        self.strategy_combo.addItem("Автоподбор")
        self.strategy_combo.addItems(strategies)
        self.strategy_combo.blockSignals(False)

        if self.saved_strategy == "auto_found.bat":
            self.strategy_combo.setCurrentText("Автоподбор")
        elif self.saved_strategy in strategies:
            self.strategy_combo.setCurrentText(self.saved_strategy)
        else:
            self.strategy_combo.setCurrentIndex(0)

        self.start_btn.setEnabled(True)

    def check_for_update(self):
        try:
            r = requests.get(
                "https://api.github.com/repos/rosakodu/zapretdeck/releases/latest",
                headers={'User-Agent': 'ZapretDeck/1.0'}, timeout=8
            )
            data = r.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
            latest_version = version.parse(latest_tag)
            current_version = version.parse(CURRENT_VERSION)

            if latest_version > current_version:
                self.update_label.setText(f"Доступно: v{latest_tag}")
                self.show_msg("Обновление", f"Вышла новая версия: v{latest_tag}\nПерейдите на GitHub для загрузки.")
                self.version_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #ff6b6b;")
            else:
                self.version_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #107C10;")
        except Exception as e:
            logger.debug(f"Update check failed: {e}")

    def closeEvent(self, event):
        self.loading_timer.stop()
        event.accept()


if __name__ == "__main__":
    os.environ["QT_PLUGIN_PATH"] = "/usr/lib/qt6/plugins"
    os.environ["QT_QPA_PLATFORMTHEME"] = "qt6ct"

    app = QApplication(sys.argv)
    print(f"[ZapretDeck] Запуск v{CURRENT_VERSION}")

    window = ZapretGUI()
    window.showMaximized()
    sys.exit(app.exec())