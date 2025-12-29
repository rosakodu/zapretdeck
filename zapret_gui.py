#!/usr/bin/env python3
import os
import subprocess
import sys
import logging
import shutil
import webbrowser
from packaging import version
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFrame, QMessageBox,
    QInputDialog, QLineEdit, QGridLayout, QCheckBox, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QCursor

# === ПУТИ ===
BASE_DIR = "/opt/zapretdeck"
REPO_DIR = os.path.join(BASE_DIR, "zapret-latest")
CONF_FILE = os.path.join(BASE_DIR, "conf.env")
MAIN_SCRIPT = os.path.join(BASE_DIR, "main_script.sh")
STOP_SCRIPT = os.path.join(BASE_DIR, "stop_and_clean_nft.sh")
DNS_SCRIPT = os.path.join(BASE_DIR, "dns.sh")
RENAME_SCRIPT = os.path.join(BASE_DIR, "rename_bat.sh")
SERVICE_SCRIPT = os.path.join(BASE_DIR, "service.sh")
LOG_FILE = "/opt/zapretdeck/debug.log"

# === ЛОГИ ===
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    filemode='a'
)
logger = logging.getLogger(__name__)

HIDDEN_STRATEGIES = {"check_updates.bat", "service_install.bat", "service_remove.bat", "service_status.bat"}
CURRENT_VERSION = "0.1.3"

# === МОНИТОРИНГ ===
class StatusChecker(QThread):
    session_changed = pyqtSignal(bool)
    service_changed = pyqtSignal(bool)
    dns_changed = pyqtSignal(str)

    def run(self):
        while True:
            try:
                running = subprocess.run(["pgrep", "-f", "[n]fqws"], capture_output=True).returncode == 0
                self.session_changed.emit(running)

                enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", "zapret_discord_youtube"], check=False).returncode == 0
                active = subprocess.run(["systemctl", "is-active", "--quiet", "zapret_discord_youtube"], check=False).returncode == 0
                self.service_changed.emit(enabled and active)

                provider = "disabled"
                try:
                    active_con = subprocess.run(
                        ["nmcli", "-t", "-f", "NAME", "con", "show", "--active"],
                        capture_output=True, text=True, timeout=5
                    ).stdout.strip().split('\n')
                    if active_con and active_con[0]:
                        con_name = active_con[0]
                        dns_out = subprocess.run(
                            ["nmcli", "con", "show", con_name],
                            capture_output=True, text=True, timeout=5
                        ).stdout
                        if "176.99.11.77" in dns_out or "80.78.247.254" in dns_out:
                            provider = "enabled"
                except:
                    pass
                self.dns_changed.emit(provider)

                QThread.msleep(1500)
            except Exception as e:
                logger.error(f"StatusChecker: {e}")
                QThread.msleep(1500)

# === GUI ===
class ZapretGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZapretDeck")
        self.setMinimumSize(800, 600)
        self.showMaximized()

        icon_path = os.path.join(BASE_DIR, "zapretdeck.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.sudo_password = None
        self.saved_strategy = ""
        self.dns_set_by_app = "disabled"
        self.is_running = False
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

        self.session_button = QPushButton("ПУСК")
        self.session_button.setMinimumHeight(64)
        self.session_button.clicked.connect(self.toggle_session)
        self.apply_session_style(False)
        layout.addWidget(self.session_button)

        service_row = QWidget()
        service_layout = QHBoxLayout(service_row)
        self.service_switch = QCheckBox("Работа в фоновом режиме")
        self.service_switch.stateChanged.connect(self.toggle_service)
        self.service_switch.setStyleSheet("font-size: 14px;")
        service_layout.addWidget(self.service_switch)
        service_layout.addStretch()
        layout.addWidget(service_row)

        dns_card = QFrame()
        dns_card.setProperty("class", "card")
        dns_card.setMinimumHeight(72)
        dns_layout = QHBoxLayout(dns_card)
        dns_layout.setContentsMargins(16, 12, 16, 12)

        self.dns_toggle_btn = QPushButton("xbox-dns.ru")
        self.dns_toggle_btn.setMinimumHeight(48)
        self.dns_toggle_btn.clicked.connect(self.toggle_dns)
        self.set_dns_button_state(False)
        dns_layout.addWidget(self.dns_toggle_btn)

        layout.addWidget(dns_card)

        actions_card = QFrame()
        actions_card.setProperty("class", "card")
        actions_layout = QGridLayout(actions_card)
        actions_layout.setContentsMargins(16, 16, 16, 16)
        actions_layout.setSpacing(12)

        # === КНОПКА "ЗАБРАТЬ ПРИЗ" ===
        prize_btn = QPushButton("🎁 Забрать приз 🎁")
        prize_btn.setMinimumHeight(56)
        prize_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FFD700, stop:0.5 #FFA500, stop:1 #FF8C00);
                color: white;
                border-radius: 12px;
                font-weight: bold;
                font-size: 18px;
                padding: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FFED4E, stop:0.5 #FFB84D, stop:1 #FF9D33);
            }
            QPushButton:pressed {
                background: #CC7000;
            }
        """)
        prize_btn.clicked.connect(lambda: webbrowser.open("https://t.me/deck_gift"))
        actions_layout.addWidget(prize_btn, 0, 0, 1, 2)  # на всю ширину

        # === Остальные кнопки ===
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
            actions_layout.addWidget(btn, (i // 2) + 1, i % 2)

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

    def set_dns_button_state(self, active):
        if active:
            self.dns_toggle_btn.setText("xbox-dns.ru (вкл)")
            self.dns_toggle_btn.setStyleSheet("background: #00b050; color: white; border-radius: 6px; padding: 10px; font-weight: bold; font-size: 14px;")
        else:
            self.dns_toggle_btn.setText("xbox-dns.ru")
            self.dns_toggle_btn.setStyleSheet("background: #444444; color: #e6e6e6; border-radius: 6px; padding: 10px; font-size: 14px;")

    def toggle_dns(self):
        password = self.ask_sudo_password()
        if not password:
            return
        action = "unset" if self.dns_toggle_btn.text().endswith("(вкл)") else "set"
        try:
            subprocess.run(
                ["sudo", "-S", DNS_SCRIPT, action],
                input=password + "\n", text=True, check=True, timeout=15
            )
            self.dns_set_by_app = "enabled" if action == "set" else "disabled"
            self.set_dns_button_state(action == "set")
            self.show_status(f"DNS {'включён' if action == 'set' else 'отключён'}", "#107C10")
            self.update_config()
        except Exception as e:
            logger.error(f"DNS error: {e}")
            self.show_status("Ошибка DNS", "#ff6b6b")

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
        self.checker.dns_changed.connect(self.on_system_dns_detected)
        self.checker.start()
        QTimer.singleShot(300, self.load_strategies)

    def on_session_changed(self, running):
        self.is_running = running
        self.stop_loading_animation()
        self.apply_session_style(running)

    def on_service_changed(self, state):
        self.service_switch.blockSignals(True)
        self.service_switch.setChecked(state)
        self.service_switch.blockSignals(False)

    def on_system_dns_detected(self, provider):
        is_enabled = provider == "enabled"
        if is_enabled != self.dns_toggle_btn.text().endswith("(вкл)"):
            self.set_dns_button_state(is_enabled)
            self.dns_set_by_app = provider

    def apply_session_style(self, running):
        if self.loading_timer.isActive():
            return
        text = "СТОП" if running else "ПУСК"
        grad = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #E53935,stop:1 #B71C1C)" if running else "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4CAF50,stop:1 #2E7D32)"
        self.session_button.setText(text)
        self.session_button.setStyleSheet(f"color:#fff;background:{grad};border-radius:8px;padding:16px;font-weight:bold;font-size:18px;")

    def start_loading_animation(self, action: str):
        self.loading_dots = 0
        base_text = "Запуск" if action == "start" else "Остановка"
        self.session_button.setText(f"{base_text}...")
        self.session_button.setEnabled(False)
        self.loading_timer.start(500)

    def stop_loading_animation(self):
        self.loading_timer.stop()
        self.session_button.setEnabled(True)
        self.apply_session_style(self.is_running)

    def update_loading_animation(self):
        self.loading_dots = (self.loading_dots + 1) % 4
        dots = "." * self.loading_dots
        current = self.session_button.text()
        base = current.rstrip(".")
        self.session_button.setText(f"{base}{dots}")

    def toggle_session(self):
        if self.loading_timer.isActive():
            return
        running = self.session_button.text() == "СТОП"
        password = self.ask_sudo_password()
        if not password:
            return
        if running:
            self.start_loading_animation("stop")
            QTimer.singleShot(100, lambda: self.stop_session(password))
        else:
            if not self.strategy_combo.currentText():
                self.show_status("Выбери стратегию!", "#ff6b6b")
                return
            self.start_loading_animation("start")
            QTimer.singleShot(100, lambda: self.start_session(password))

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

    def start_session(self, password):
        try:
            subprocess.run(
                ["sudo", "-S", "bash", STOP_SCRIPT],
                input=password + "\n", text=True, check=True, timeout=15
            )
        except:
            pass
        env = {
            "interface": "any",
            "strategy": self.strategy_combo.currentText(),
            "dns": "enabled" if self.dns_toggle_btn.text().endswith("(вкл)") else "disabled"
        }
        try:
            proc = subprocess.Popen(
                ["sudo", "-S", "bash", MAIN_SCRIPT, "-nointeractive"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ, **env)
            )
            stdout, stderr = proc.communicate(input=password + "\n", timeout=10)
            if proc.returncode == 0 or "nfqws" in stdout:
                self.show_status("Запущено", "#107C10")
                self.update_config()
            else:
                logger.error(f"main_script.sh error: {stderr}")
                self.show_status("Ошибка запуска", "#ff6b6b")
        except subprocess.TimeoutExpired:
            self.show_status("Запущено (в фоне)", "#107C10")
            self.update_config()
        except Exception as e:
            logger.error(f"Start error: {e}")
            self.show_status("Ошибка запуска", "#ff6b6b")
        finally:
            self.stop_loading_animation()

    def toggle_service(self):
        checked = self.service_switch.isChecked()
        password = self.ask_sudo_password()
        if not password:
            self.service_switch.blockSignals(True)
            self.service_switch.setChecked(not checked)
            self.service_switch.blockSignals(False)
            return
        try:
            if checked:
                subprocess.run(["sudo", "-S", "bash", SERVICE_SCRIPT, "install"], input=password + "\n", text=True, check=True, timeout=30)
                self.show_status("Сервис установлен", "#107C10")
            else:
                subprocess.run(["sudo", "-S", "bash", SERVICE_SCRIPT, "remove"], input=password + "\n", text=True, check=True, timeout=15)
                self.show_status("Сервис удалён", "#107C10")
        except Exception as e:
            logger.error(f"Service error: {e}")
            self.show_status("Ошибка сервиса", "#ff6b6b")
            self.service_switch.blockSignals(True)
            self.service_switch.setChecked(not checked)
            self.service_switch.blockSignals(False)

    def ask_sudo_password(self):
        if self.sudo_password:
            return self.sudo_password

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Требуется пароль")
        dialog.setLabelText("Введите ваш пароль sudo:")
        dialog.setTextEchoMode(QLineEdit.EchoMode.Password)
        dialog.resize(500, 140)

        ok_btn = dialog.findChild(QPushButton)
        if ok_btn:
            ok_btn.setText("ОК")
        buttons = dialog.findChildren(QPushButton)
        if len(buttons) > 1:
            buttons[1].setText("Отменить")

        if dialog.exec() == QInputDialog.DialogCode.Accepted:
            pw = dialog.textValue()
            if subprocess.run(["sudo", "-S", "true"], input=pw + "\n", text=True, capture_output=True).returncode == 0:
                self.sudo_password = pw
                return pw
            self.show_status("Неверный пароль", "#ff6b6b")
        return None

    def show_status(self, text, color, timeout=2000):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 14px;")
        QTimer.singleShot(timeout, lambda: self.status_label.setText("") if self.status_label.text() == text else None)

    def show_msg(self, title, text):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.addButton("ОК", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Отменить", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

    def update_config(self, source=None):
        try:
            with open(CONF_FILE, "w") as f:
                f.write(f"interface=any\n")
                f.write(f"strategy={self.strategy_combo.currentText()}\n")
                f.write(f"dns={'enabled' if self.dns_toggle_btn.text().endswith('(вкл)') else 'disabled'}\n")
                f.write(f"dns_set_by_app={self.dns_set_by_app}\n")
            if source != "silent":
                self.show_status("Настройки сохранены", "#107C10")
        except Exception as e:
            logger.error(f"update_config: {e}")

    def load_config(self):
        if os.path.exists(CONF_FILE):
            with open(CONF_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("strategy="):
                        self.saved_strategy = line.split("=", 1)[1]
                    elif line.startswith("dns_set_by_app="):
                        self.dns_set_by_app = line.split("=", 1)[1]
        self.load_strategies()

    def check_dependencies(self):
        deps = ['ip', 'nft', 'systemctl', 'pgrep', 'pkill', 'bash', 'nmcli', 'curl']
        return all(shutil.which(d) for d in deps)

    def load_strategies(self):
        if not os.path.exists(REPO_DIR):
            self.show_status("zapret-latest не найден!", "#ff6b6b")
            return
        try:
            if os.path.exists(RENAME_SCRIPT):
                subprocess.run(["bash", RENAME_SCRIPT], cwd=BASE_DIR)
            strategies = [f for f in os.listdir(REPO_DIR) if f.endswith(".bat") and f not in HIDDEN_STRATEGIES]
            self.strategy_combo.blockSignals(True)
            self.strategy_combo.clear()
            self.strategy_combo.addItems(strategies)
            self.strategy_combo.blockSignals(False)
            if self.saved_strategy in strategies:
                self.strategy_combo.setCurrentText(self.saved_strategy)
            self.session_button.setEnabled(bool(strategies))
            self.update_config("silent")
        except Exception as e:
            logger.error(f"load_strategies: {e}")

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

    def on_strategy_changed(self, text):
        if text and self.is_running:
            password = self.ask_sudo_password()
            if password:
                self.start_loading_animation("stop")
                QTimer.singleShot(100, lambda: self.stop_session(password))
                self.show_status("Стратегия изменена — перезапуск", "#ff6b6b", 2500)
            else:
                self.strategy_combo.blockSignals(True)
                self.strategy_combo.setCurrentText(self.saved_strategy)
                self.strategy_combo.blockSignals(False)
        else:
            self.update_config()

    def closeEvent(self, event):
        self.loading_timer.stop()
        event.accept()


# === ЗАПУСК ===
if __name__ == "__main__":
    os.environ["QT_PLUGIN_PATH"] = "/usr/lib/qt6/plugins"
    os.environ["QT_QPA_PLATFORMTHEME"] = "qt6ct"

    app = QApplication(sys.argv)
    print(f"[ZapretDeck] Запуск v{CURRENT_VERSION}")

    window = ZapretGUI()
    window.showMaximized()
    sys.exit(app.exec())