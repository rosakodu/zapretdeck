#!/usr/bin/env python3
import os
import subprocess
import customtkinter as ctk
from tkinter import Canvas, PhotoImage, messagebox
import webbrowser
import time
import shutil
import logging
import requests  # Для HTTP-запросов к GitHub
import tarfile  # Для работы с tar.gz архивами

# Настройка логирования
logging.basicConfig(filename='/opt/zapretdeck/debug.log', level=logging.INFO, format='%(asctime)s [DEBUG] %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
REPO_DIR = os.path.join(BASE_DIR, "zapret-latest")
CONF_FILE = os.path.join(BASE_DIR, "conf.env")
MAIN_SCRIPT = os.path.join(BASE_DIR, "main_script.sh")
STOP_SCRIPT = os.path.join(BASE_DIR, "stop_and_clean_nft.sh")
DNS_SCRIPT = os.path.join(BASE_DIR, "dns.sh")
VERSION_FILE = os.path.join(BASE_DIR, "version.txt")
GITHUB_REPO = "rosakodu/zapretdeck"  # Обновлено на ваш репозиторий
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Цвета в QT-стиле
COLOR_BG = "#242424"
COLOR_ACCENT = "#0078D4"  # QT синий
COLOR_GREEN = "#107C10"  # QT зелёный
COLOR_RED = "#C50F1F"  # QT красный
COLOR_WHITE = "#FFFFFF"
COLOR_GRAY = "#5C5C5C"
COLOR_LIGHT_GRAY = "#B3B3B3"

class SudoPasswordDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Пароль sudo")
        self.geometry("320x180")
        self.transient(parent)
        self.configure(fg_color=COLOR_BG)
        self.password = None
        title = ctk.CTkLabel(self, text="Введите пароль для sudo:", font=("Inter", 14, "bold"), text_color=COLOR_WHITE)
        title.pack(pady=10)
        self.entry = ctk.CTkEntry(self, show="*", width=220, height=30, font=("Inter", 12), fg_color="#333333", border_color=COLOR_ACCENT)
        self.entry.pack(pady=5)
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda event: self.submit())
        self.bind("<Escape>", lambda event: self.cancel())
        ok_btn = ctk.CTkButton(self, text="OK", command=self.submit, font=("Inter", 12, "bold"), fg_color=COLOR_ACCENT, height=30)
        ok_btn.pack(pady=5, side="left", padx=10)
        cancel_btn = ctk.CTkButton(self, text="Отмена", command=self.cancel, font=("Inter", 12), fg_color=COLOR_GRAY, height=30)
        cancel_btn.pack(pady=5, side="right", padx=10)
        self.after(100, self._grab_set_safe)
    def _grab_set_safe(self):
        if self.winfo_exists() and self.winfo_viewable():
            self.grab_set()
        else:
            self.after(100, self._grab_set_safe)
    def submit(self):
        self.password = self.entry.get()
        self.grab_release()
        self.destroy()
    def cancel(self):
        self.password = None
        self.grab_release()
        self.destroy()

class RoundButton(Canvas):
    def __init__(self, parent, text, command, fg_color=COLOR_GREEN, size=150, **kwargs):
        super().__init__(parent, width=size, height=size, highlightthickness=0, bg=COLOR_BG, **kwargs)
        self.text = text
        self.command = command
        self.fg_color = fg_color
        self.size = size
        self.enabled = True
        self.bind("<Button-1>", self._on_click)
        self.draw()
    def draw(self):
        self.delete("all")
        if self.enabled:
            self.create_oval(5, 5, self.size-5, self.size-5, fill=self.fg_color, outline=COLOR_WHITE, width=2)
            self.create_text(self.size/2, self.size/2, text=self.text, font=("Inter", 22, "bold"), fill=COLOR_WHITE)
        else:
            self.create_oval(5, 5, self.size-5, self.size-5, fill=COLOR_GRAY, outline=COLOR_WHITE, width=2)
            self.create_text(self.size/2, self.size/2, text=self.text, font=("Inter", 22, "bold"), fill=COLOR_LIGHT_GRAY)
    def configure(self, **kwargs):
        if "text" in kwargs:
            self.text = kwargs["text"]
        if "fg_color" in kwargs:
            self.fg_color = kwargs["fg_color"]
        if "state" in kwargs:
            self.enabled = kwargs["state"] != "disabled"
        self.draw()
    def _on_click(self, event):
        if self.enabled and self.command:
            self.command()

class ZapretGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ZapretDeck")
        self.geometry("350x430")
        self.minsize(350, 430)
        self.maxsize(350, 650)
        self.session_process = None
        self.sudo_password = None
        self.configure(fg_color=COLOR_BG)
        self.warning_label = None  # Persistent warning for missing strategies
        icon_path = os.path.join(BASE_DIR, "zapretdeck.png")
        if os.path.exists(icon_path):
            icon = PhotoImage(file=icon_path)
            self.wm_iconphoto(True, icon)
        self.protocol("WM_DELETE_WINDOW", self.on_exit)  # Handle window close
        if not self.check_dependencies():
            logger.error("Завершение из-за отсутствия зависимостей")
            self.quit()
            return
        # Show loading indicator
        self.loading_label = ctk.CTkLabel(self, text="Загрузка...", font=("Inter", 12), text_color=COLOR_WHITE)
        self.loading_label.pack(pady=10)
        self.update()
        self.after(100, self.setup_ui)
        self.after(1000, self.check_session_status)

    def setup_ui(self):
        self.loading_label.destroy()  # Remove loading label
        self.main_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=COLOR_BG)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        version = self.load_version()
        beta_label = ctk.CTkLabel(self.main_frame, text=f"Бета {version}", font=("Inter", 12, "bold"), text_color=COLOR_ACCENT)
        beta_label.pack(anchor="n", pady=5)

        interface_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        interface_frame.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(interface_frame, text="Сетевой интерфейс:", font=("Inter", 12, "bold"), text_color=COLOR_WHITE).pack(anchor="w", pady=(0, 2))
        self.interface_var = ctk.StringVar()
        interfaces = self.get_active_interfaces()
        self.interface_combo = ctk.CTkComboBox(interface_frame, values=interfaces, variable=self.interface_var,
                                              state="readonly", font=("Inter", 11), width=220, height=30,
                                              fg_color="#2E2E2E", button_color=COLOR_ACCENT, border_color=COLOR_ACCENT)
        self.interface_combo.pack(pady=2)
        self.interface_combo.bind("<<ComboboxSelected>>", lambda e: self.update_config("interface"))

        strategy_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        strategy_frame.pack(fill="x", padx=5, pady=2)
        ctk.CTkLabel(strategy_frame, text="Стратегия:", font=("Inter", 12, "bold"), text_color=COLOR_WHITE).pack(anchor="w", pady=(0, 2))
        self.strategy_var = ctk.StringVar()
        self.strategy_combo = ctk.CTkComboBox(strategy_frame, variable=self.strategy_var,
                                              state="readonly", font=("Inter", 11), width=220, height=30,
                                              fg_color="#2E2E2E", button_color=COLOR_ACCENT, border_color=COLOR_ACCENT)
        self.strategy_combo.pack(pady=2)
        self.strategy_combo.bind("<<ComboboxSelected>>", lambda e: self.update_config("strategy"))

        button_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        button_container.pack(pady=10)
        self.session_button = RoundButton(button_container, text="▶ Пуск", command=self.toggle_session,
                                         fg_color=COLOR_GREEN, size=150)
        self.session_button.pack()

        switch_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        switch_frame.pack(fill="x", padx=5, pady=2)

        self.service_enable_switch = ctk.CTkSwitch(switch_frame, text="Автозапуск", command=self.toggle_service,
                                                  font=("Inter", 11), width=220, height=30,
                                                  progress_color=COLOR_ACCENT)
        self.service_enable_switch.pack(anchor="w", pady=2)

        self.dns_switch = ctk.CTkSwitch(switch_frame, text="DNS", command=self.toggle_dns,
                                        font=("Inter", 11), width=220, height=30,
                                        progress_color=COLOR_ACCENT)
        self.dns_switch.pack(anchor="w", pady=2)

        button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        button_frame.pack(fill="x", padx=5, pady=2)

        ctk.CTkButton(button_frame, text="Проверить обновление", command=self.check_update,
                      font=("Inter", 11), height=30, fg_color="#2E2E2E", border_color=COLOR_ACCENT).pack(fill="x", pady=2)
        ctk.CTkButton(button_frame, text="ВКонтакте", command=lambda: webbrowser.open("https://vk.com/valvesteamdeck"),
                      font=("Inter", 11), height=30, fg_color="#2E2E2E", border_color=COLOR_ACCENT).pack(fill="x", pady=2)
        ctk.CTkButton(button_frame, text="Telegram", command=lambda: webbrowser.open("https://t.me/deckru"),
                      font=("Inter", 11), height=30, fg_color="#2E2E2E", border_color=COLOR_ACCENT).pack(fill="x", pady=2)
        ctk.CTkButton(button_frame, text="МАХ", command=lambda: webbrowser.open("https://max.ru/valvesteamdeck"),
                      font=("Inter", 11), height=30, fg_color="#2E2E2E", border_color=COLOR_ACCENT).pack(fill="x", pady=2)

        exit_btn = ctk.CTkButton(self.main_frame, text="Выход", command=self.on_exit, fg_color=COLOR_RED,
                                 font=("Inter", 11, "bold"), height=35, border_width=0)
        exit_btn.pack(pady=5)

        self.load_config()
        self.check_service_status()
        self.check_dns_status()
        self.load_strategies()
        self.check_session_status()

    def check_dependencies(self):
        """Проверяет наличие необходимых зависимостей."""
        deps = ['ip', 'nft', 'systemctl']
        for dep in deps:
            if subprocess.run(['which', dep], capture_output=True).returncode != 0:
                messagebox.showerror("Ошибка", f"Не найдена зависимость: {dep}")
                return False
        return True

    def get_active_interfaces(self):
        """Получает список активных сетевых интерфейсов."""
        try:
            result = subprocess.run(["ip", "link", "show"], capture_output=True, text=True)
            interfaces = []
            for line in result.stdout.split('\n'):
                if 'state UP' in line:
                    interface = line.split(':')[1].strip().split('@')[0]
                    if interface not in ['lo']:
                        interfaces.append(interface)
            return interfaces + ['any']
        except:
            return ['any']

    def load_strategies(self):
        """Загружает список доступных стратегий."""
        strategies = []
        if os.path.exists(REPO_DIR):
            for file in os.listdir(REPO_DIR):
                if file.endswith('.bat'):
                    strategies.append(file)
        self.strategy_combo.configure(values=strategies)
        if strategies:
            self.strategy_var.set(strategies[0])
        else:
            if self.warning_label:
                self.warning_label.destroy()
            self.warning_label = ctk.CTkLabel(self.main_frame, text="Нет доступных стратегий!", text_color=COLOR_RED, font=("Inter", 11))
            self.warning_label.pack(pady=2)

    def load_config(self):
        """Загружает конфигурацию."""
        if os.path.exists(CONF_FILE):
            with open(CONF_FILE, 'r') as f:
                for line in f:
                    if '=' in line:
                        key, value = line.strip().split('=', 1)
                        if key == 'interface':
                            self.interface_var.set(value)
                        elif key == 'strategy':
                            self.strategy_var.set(value)
                        elif key == 'dns' and value == 'enabled':
                            self.dns_switch.select()
                        elif key == 'auto_update' and value == 'true':
                            self.check_update()

    def update_config(self, key):
        """Обновляет конфигурацию."""
        config = {}
        if os.path.exists(CONF_FILE):
            with open(CONF_FILE, 'r') as f:
                for line in f:
                    if '=' in line:
                        k, v = line.strip().split('=', 1)
                        config[k] = v
        config[key] = self.__dict__[f"{key}_var"].get() if key in ['interface', 'strategy'] else 'enabled' if self.dns_switch.get() else 'disabled'
        with open(CONF_FILE, 'w') as f:
            for k, v in config.items():
                f.write(f"{k}={v}\n")

    def check_session_status(self):
        """Проверяет статус сессии."""
        try:
            result = subprocess.run(["pgrep", "-f", "nfqws"], capture_output=True, text=True)
            if result.returncode == 0:
                if not self.session_process:
                    self.session_button.configure(text="⏹ Стоп", fg_color=COLOR_RED, state="normal")
                return
            if self.session_process:
                try:
                    self.session_process.poll()
                    if self.session_process.returncode is not None:
                        self.session_process = None
                        self.session_button.configure(text="▶ Пуск", fg_color=COLOR_GREEN, state="normal")
                except:
                    self.session_process = None
                    self.session_button.configure(text="▶ Пуск", fg_color=COLOR_GREEN, state="normal")
            else:
                self.session_button.configure(text="▶ Пуск", fg_color=COLOR_GREEN, state="normal")
        except Exception as e:
            logger.error(f"Ошибка проверки статуса сессии: {e}")

    def check_service_status(self):
        """Проверяет статус сервиса."""
        try:
            result = subprocess.run(["systemctl", "is-active", "zapret_discord_youtube"], capture_output=True, text=True)
            if result.returncode == 0:
                self.service_enable_switch.select()
            else:
                self.service_enable_switch.deselect()
        except:
            self.service_enable_switch.deselect()

    def check_dns_status(self):
        """Проверяет статус DNS."""
        if not os.path.exists(DNS_SCRIPT):
            logger.error(f"Скрипт DNS не найден: {DNS_SCRIPT}")
            self.dns_switch.deselect()
            return
        try:
            result = subprocess.run([DNS_SCRIPT, "check"], capture_output=True, text=True)
            if result.returncode == 0:
                self.dns_switch.select()
            else:
                self.dns_switch.deselect()
        except:
            self.dns_switch.deselect()

    def load_version(self):
        """Загружает текущую версию."""
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r") as f:
                return f.read().strip()
        return "0.0.1"

    def get_latest_version(self):
        """Получает последнюю версию из GitHub релиза."""
        try:
            response = requests.get(GITHUB_API_LATEST, timeout=10)
            response.raise_for_status()
            release_data = response.json()
            latest_version = release_data['tag_name'].lstrip('v')  # Убираем 'v' из тега (напр., v0.0.1 -> 0.0.1)
            logger.info(f"Последняя версия на GitHub: {latest_version}")
            return latest_version, release_data
        except Exception as e:
            logger.error(f"Ошибка получения версии с GitHub: {e}")
            return None, None

    def compare_versions(self, current, latest):
        """Сравнивает версии (простое строковое сравнение)."""
        try:
            current_parts = [int(x) for x in current.split('.')]
            latest_parts = [int(x) for x in latest.split('.')]
            return latest_parts > current_parts
        except:
            return False

    def download_and_update(self, latest_version, release_data):
        """Скачивает и устанавливает обновление."""
        try:
            # Получаем имя архива из релиза
            assets = release_data.get('assets', [])
            archive_url = None
            archive_name = None
            for asset in assets:
                if asset['name'].endswith('.tar.gz'):
                    archive_url = asset['browser_download_url']
                    archive_name = asset['name']
                    break
            
            if not archive_url:
                raise Exception("Архив .tar.gz не найден в релизе")

            temp_dir = "/tmp/zapretdeck-update"
            os.makedirs(temp_dir, exist_ok=True)
            archive_path = os.path.join(temp_dir, archive_name)

            # Показываем индикатор загрузки
            status_label = ctk.CTkLabel(self.main_frame, text="Загрузка обновления...", text_color=COLOR_ACCENT, font=("Inter", 11))
            status_label.pack(pady=2)
            self.update()

            # Скачиваем архив
            response = requests.get(archive_url, stream=True, timeout=30)
            response.raise_for_status()
            with open(archive_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"Архив скачан: {archive_path}")

            status_label.destroy()

            # Запрашиваем пароль sudo
            password = self.ask_sudo_password()
            if not password:
                raise Exception("Пароль sudo не предоставлен")

            # Останавливаем процессы
            subprocess.run(["sudo", "-S", "systemctl", "stop", "zapret_discord_youtube"], input=password + "\n", text=True, capture_output=True)
            subprocess.run(["sudo", "-S", "pkill", "-f", "nfqws"], input=password + "\n", text=True, capture_output=True)
            subprocess.run(["sudo", "-S", "nft", "flush", "ruleset"], input=password + "\n", text=True, capture_output=True)

            # Распаковываем архив
            with tarfile.open(archive_path, 'r:gz') as tar:
                tar.extractall(temp_dir)

            # Определяем извлечённую директорию
            extracted_files = os.listdir(temp_dir)
            extracted_dir = None
            for item in extracted_files:
                full_path = os.path.join(temp_dir, item)
                if os.path.isdir(full_path) and (item.startswith('zapretdeck') or item.startswith('ZapretDeck')):
                    extracted_dir = full_path
                    break
            if not extracted_dir:
                extracted_dir = temp_dir  # Если файлы распакованы прямо в temp_dir

            # Копируем файлы
            for item in os.listdir(extracted_dir):
                src = os.path.join(extracted_dir, item)
                dst = os.path.join(BASE_DIR, item)
                if os.path.isdir(src):
                    shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)

            # Устанавливаем права
            subprocess.run(["sudo", "-S", "chmod", "+x", f"{REPO_DIR}/nfqws"], input=password + "\n", text=True, capture_output=True)
            subprocess.run(["sudo", "-S", "chmod", "+x", MAIN_SCRIPT], input=password + "\n", text=True, capture_output=True)
            subprocess.run(["sudo", "-S", "chmod", "+x", STOP_SCRIPT], input=password + "\n", text=True, capture_output=True)
            subprocess.run(["sudo", "-S", "chmod", "+x", DNS_SCRIPT], input=password + "\n", text=True, capture_output=True)

            # Обновляем версию
            with open(VERSION_FILE, 'w') as f:
                f.write(latest_version)

            # Перезагружаем systemd
            subprocess.run(["sudo", "-S", "systemctl", "daemon-reload"], input=password + "\n", text=True, capture_output=True)

            # Очистка
            shutil.rmtree(temp_dir, ignore_errors=True)

            status_label = ctk.CTkLabel(self.main_frame, text=f"Обновление до {latest_version} завершено! Перезапустите приложение.", text_color=COLOR_GREEN, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(5000, status_label.destroy)
            logger.info(f"Обновление завершено: {latest_version}")

        except Exception as e:
            logger.error(f"Ошибка обновления: {e}")
            status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка обновления: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(5000, status_label.destroy)

    def check_update(self):
        """Проверяет и устанавливает обновление."""
        self.loading_label = ctk.CTkLabel(self.main_frame, text="Проверка обновлений...", text_color=COLOR_ACCENT, font=("Inter", 11))
        self.loading_label.pack(pady=2)
        self.update()

        current_version = self.load_version()
        latest_version, release_data = self.get_latest_version()

        self.loading_label.destroy()

        if not latest_version:
            status_label = ctk.CTkLabel(self.main_frame, text="Не удалось проверить обновления", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
            return

        if self.compare_versions(current_version, latest_version):
            if messagebox.askyesno("Обновление доступно", f"Доступна новая версия {latest_version}\nТекущая: {current_version}\n\nОбновить?"):
                self.download_and_update(latest_version, release_data)
        else:
            status_label = ctk.CTkLabel(self.main_frame, text=f"Версия актуальна: {current_version}", text_color=COLOR_GREEN, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(2000, status_label.destroy)

    def ask_sudo_password(self):
        """Показывает диалог ввода пароля sudo и возвращает пароль."""
        dialog = SudoPasswordDialog(self)
        self.wait_window(dialog)
        return dialog.password

    def toggle_session(self):
        if self.session_button.text == "▶ Пуск":
            if not os.path.exists(MAIN_SCRIPT):
                logger.error(f"Скрипт не найден: {MAIN_SCRIPT}")
                status_label = ctk.CTkLabel(self.main_frame, text="Скрипт не найден!", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                return
            if not os.access(MAIN_SCRIPT, os.X_OK):
                logger.error(f"Скрипт не имеет прав на выполнение: {MAIN_SCRIPT}")
                status_label = ctk.CTkLabel(self.main_frame, text="Скрипт не исполняемый!", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                return
            if not self.strategy_var.get() or not os.path.exists(os.path.join(REPO_DIR, self.strategy_var.get())):
                logger.error(f"Недействительная стратегия: {self.strategy_var.get()}")
                status_label = ctk.CTkLabel(self.main_frame, text="Выберите действующую стратегию!", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                return
            if self.interface_var.get() == "":
                logger.error("Не выбран сетевой интерфейс")
                status_label = ctk.CTkLabel(self.main_frame, text="Выберите сетевой интерфейс!", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                return
            password = self.ask_sudo_password()
            if not password:
                return
            self.session_button.configure(state="disabled")
            self.update()
            self.config(cursor="wait")
            try:
                env = os.environ.copy()
                env['interface'] = self.interface_var.get()
                env['strategy'] = os.path.join(REPO_DIR, self.strategy_var.get())
                self.session_process = subprocess.Popen(["sudo", "-S", MAIN_SCRIPT], stdin=subprocess.PIPE, env=env, text=True)
                self.session_process.stdin.write(password + "\n")
                self.session_process.stdin.flush()
                time.sleep(1)
                logger.info(f"Сессия запущена с interface={self.interface_var.get()}, strategy={self.strategy_var.get()}")
                status_label = ctk.CTkLabel(self.main_frame, text="Сессия запущена", text_color=COLOR_GREEN, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(2000, status_label.destroy)
                self.session_button.configure(text="⏹ Стоп", fg_color=COLOR_RED, state="normal")
                self.update()
                self.config(cursor="")
            except Exception as e:
                logger.error(f"Ошибка запуска сессии: {e}")
                self.session_process = None
                status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка запуска сессии: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.session_button.configure(state="normal")
                self.update()
                self.config(cursor="")
        else:
            password = self.ask_sudo_password()
            if not password:
                self.session_button.configure(state="normal")
                self.update()
                self.config(cursor="")
                return
            try:
                subprocess.run(["sudo", "-S", "nft", "flush", "ruleset"], input=password + "\n", text=True, capture_output=True, check=True)
                subprocess.run(["sudo", "-S", "pkill", "-f", "nfqws"], input=password + "\n", text=True, capture_output=True)
                if self.session_process:
                    self.session_process.terminate()
                    try:
                        self.session_process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self.session_process.kill()
                self.session_process = None
                time.sleep(1)
                logger.info("Сессия остановлена")
                status_label = ctk.CTkLabel(self.main_frame, text="Сессия остановлена", text_color=COLOR_GREEN, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(2000, status_label.destroy)
                self.session_button.configure(text="▶ Пуск", fg_color=COLOR_GREEN, state="normal")
                self.update()
                self.config(cursor="")
            except Exception as e:
                logger.error(f"Ошибка остановки сессии: {e}")
                self.session_process = None
                status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка остановки сессии: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.session_button.configure(text="▶ Пуск", fg_color=COLOR_GREEN, state="normal")
                self.update()
                self.config(cursor="")
        self.check_session_status()

    def create_systemd_service(self):
        if not os.path.exists(MAIN_SCRIPT) or not os.path.exists(STOP_SCRIPT):
            logger.error(f"Не найдены скрипты: {MAIN_SCRIPT} или {STOP_SCRIPT}")
            status_label = ctk.CTkLabel(self.main_frame, text="Скрипты сервиса не найдены!", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
            return
        if not self.strategy_var.get() or not os.path.exists(os.path.join(REPO_DIR, self.strategy_var.get())):
            logger.error(f"Недействительная стратегия для сервиса: {self.strategy_var.get()}")
            status_label = ctk.CTkLabel(self.main_frame, text="Выберите действующую стратегию!", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
            return
        unit_file = f"""[Unit]
Description=Zapret Discord/YouTube
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={BASE_DIR}
User=root
EnvironmentFile={CONF_FILE}
ExecStart=/usr/bin/env bash {MAIN_SCRIPT} -nointeractive
ExecStop=/usr/bin/env bash {STOP_SCRIPT}
ExecStopPost=/usr/bin/env echo "Сервис завершён"
StandardOutput=append:/opt/zapretdeck/debug.log
StandardError=append:/opt/zapretdeck/debug.log

[Install]
WantedBy=multi-user.target
"""
        try:
            tmp_path = "/tmp/zapret_discord_youtube.service"
            with open(tmp_path, "w") as f:
                f.write(unit_file)
            password = self.ask_sudo_password()
            if not password:
                return
            subprocess.run(["sudo", "-S", "mv", tmp_path, "/etc/systemd/system/zapret_discord_youtube.service"], input=password + "\n", text=True, check=True)
            subprocess.run(["sudo", "-S", "systemctl", "daemon-reload"], input=password + "\n", text=True, check=True)
        except Exception as e:
            logger.error(f"Ошибка создания сервиса: {e}")
            status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка создания сервиса: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)

    def toggle_service(self):
        if self.interface_var.get() == "" or self.strategy_var.get() == "":
            logger.error(f"Не выбраны интерфейс или стратегия для автозапуска: interface={self.interface_var.get()}, strategy={self.strategy_var.get()}")
            status_label = ctk.CTkLabel(self.main_frame, text="Выберите интерфейс и стратегию для автозапуска!", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
            self.service_enable_switch.deselect()
            self.update()
            self.config(cursor="")
            return
        if self.service_enable_switch.get():
            password = self.ask_sudo_password()
            if not password:
                self.service_enable_switch.deselect()
                self.update()
                self.config(cursor="")
                return
            try:
                result = subprocess.run(["systemctl", "cat", "zapret_discord_youtube"], capture_output=True, text=True)
                if result.returncode != 0 or not os.path.exists(os.path.join(REPO_DIR, self.strategy_var.get())):
                    self.create_systemd_service()
                subprocess.run(["sudo", "-S", "systemctl", "enable", "--now", "zapret_discord_youtube"], input=password + "\n", text=True, check=True)
                logger.info("Сервис запущен")
                status_label = ctk.CTkLabel(self.main_frame, text="Сервис запущен", text_color=COLOR_GREEN, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(2000, status_label.destroy)
                self.check_session_status()
                self.update()
                self.config(cursor="")
            except Exception as e:
                logger.error(f"Ошибка запуска сервиса: {e}")
                self.service_enable_switch.deselect()
                status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка запуска сервиса: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.update()
                self.config(cursor="")
        else:
            password = self.ask_sudo_password()
            if not password:
                self.service_enable_switch.select()
                self.update()
                self.config(cursor="")
                return
            try:
                subprocess.run(["sudo", "-S", "systemctl", "disable", "--now", "zapret_discord_youtube"], input=password + "\n", text=True, check=True)
                logger.info("Сервис остановлен")
                status_label = ctk.CTkLabel(self.main_frame, text="Сервис остановлен", text_color=COLOR_GREEN, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(2000, status_label.destroy)
                self.check_session_status()
                self.update()
                self.config(cursor="")
            except Exception as e:
                logger.error(f"Ошибка остановки сервиса: {e}")
                self.service_enable_switch.select()
                status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка остановки сервиса: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.update()
                self.config(cursor="")

    def toggle_dns(self):
        if not os.path.exists(DNS_SCRIPT):
            logger.error(f"Скрипт DNS не найден: {DNS_SCRIPT}")
            self.dns_switch.deselect()
            status_label = ctk.CTkLabel(self.main_frame, text="Скрипт DNS не найден!", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
            self.update()
            self.config(cursor="")
            return
        if not os.access(DNS_SCRIPT, os.X_OK):
            logger.error(f"Скрипт DNS не имеет прав на выполнение: {DNS_SCRIPT}")
            self.dns_switch.deselect()
            status_label = ctk.CTkLabel(self.main_frame, text="Скрипт DNS не исполняемый!", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
            self.update()
            self.config(cursor="")
            return
        password = self.ask_sudo_password()
        if not password:
            logger.error("Пароль sudo не предоставлен")
            self.dns_switch.deselect() if self.dns_switch.get() else self.dns_switch.select()
            status_label = ctk.CTkLabel(self.main_frame, text="Пароль sudo не предоставлен!", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
            self.update()
            self.config(cursor="")
            return
        try:
            action = "set" if self.dns_switch.get() else "unset"
            logger.info(f"Выполнение команды: sudo -S {DNS_SCRIPT} {action}")
            result = subprocess.run(["sudo", "-S", DNS_SCRIPT, action], input=password + "\n", text=True, capture_output=True, check=True)
            logger.info(f"DNS {action}: stdout={result.stdout}, stderr={result.stderr}")
            self.check_dns_status()
            self.update_config("dns")
            status_label = ctk.CTkLabel(self.main_frame, text=f"DNS {'включён' if self.dns_switch.get() else 'отключён'}", text_color=COLOR_GREEN, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(2000, status_label.destroy)
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка выполнения DNS-скрипта: {e}, stdout={e.stdout}, stderr={e.stderr}")
            self.check_dns_status()
            status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка DNS: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
        except Exception as e:
            logger.error(f"Неизвестная ошибка при выполнении DNS-скрипта: {e}")
            self.check_dns_status()
            status_label = ctk.CTkLabel(self.main_frame, text=f"Неизвестная ошибка DNS: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
        self.update()
        self.config(cursor="")

    def on_exit(self):
        if self.session_button.text == "⏹ Стоп" and not self.service_enable_switch.get():
            if messagebox.askyesno("Подтверждение", "Сессия активна. Продолжить в фоне?"):
                logger.info("Сессия активна, сохраняем её при выходе")
                self.session_process = None  # Detach process
            else:
                password = self.ask_sudo_password()
                if password:
                    try:
                        subprocess.run(["sudo", "-S", "nft", "flush", "ruleset"], input=password + "\n", text=True, capture_output=True, check=True)
                        subprocess.run(["sudo", "-S", "pkill", "-f", "nfqws"], input=password + "\n", text=True, capture_output=True)
                        if self.session_process:
                            self.session_process.terminate()
                            try:
                                self.session_process.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                self.session_process.kill()
                        logger.info("Сессия остановлена при выходе")
                    except Exception as e:
                        logger.error(f"Ошибка остановки сессии при выходе: {e}")
                self.session_process = None
        self.sudo_password = None
        self.quit()

if __name__ == "__main__":
    try:
        app = ZapretGUI()
        app.mainloop()
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске приложения: {e}")
        raise
