#!/usr/bin/env python3
import os
import subprocess
import customtkinter as ctk
from tkinter import Canvas, PhotoImage, messagebox
import webbrowser
import time
import shutil
import logging
import requests
from packaging import version

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

        self.dns_switch = ctk.CTkSwitch(switch_frame, text="xbox-dns.ru", command=self.toggle_dns,
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

    def load_version(self):
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r") as f:
                return f.read().strip()
        return "0.0.2"

    def check_dependencies(self):
        deps = ['ip', 'nft', 'systemctl', 'pgrep', 'pkill', 'bash', 'curl', 'git', 'nmcli']
        missing = [d for d in deps if shutil.which(d) is None]
        if missing:
            logger.error(f"Отсутствуют зависимости: {', '.join(missing)}")
            return False
        try:
            import requests
            import packaging.version
        except ImportError as e:
            logger.error(f"Отсутствует модуль: {e.name}")
            return False
        return True

    def get_active_interfaces(self):
        try:
            result = subprocess.run(['ip', 'link', 'show', 'up'], capture_output=True, text=True)
            interfaces = [line.split(':')[1].strip() for line in result.stdout.splitlines() if ':' in line and 'state UP' in line]
            return [i for i in interfaces if i != 'lo'] + ['any']
        except Exception as e:
            logger.error(f"Ошибка получения интерфейсов: {e}")
            return ['any']

    def check_session_status(self):
        try:
            result = subprocess.run(["pgrep", "-f", "nfqws"], capture_output=True, text=True)
            is_running = result.returncode == 0
            if is_running and self.session_button.text != "⏹ Стоп":
                logger.info("Обнаружены процессы nfqws, синхронизация состояния кнопки")
                self.session_button.configure(text="⏹ Стоп", fg_color=COLOR_RED)
            elif not is_running and self.session_button.text != "▶ Пуск":
                logger.info("Процессы nfqws не найдены, завершение сессии")
                self.session_process = None
                self.session_button.configure(text="▶ Пуск", fg_color=COLOR_GREEN)
            self.after(1000, self.check_session_status)
        except Exception as e:
            logger.error(f"Ошибка проверки статуса сессии: {e}")

    def check_service_status(self):
        try:
            result = subprocess.run(["systemctl", "is-enabled", "zapret_discord_youtube"], capture_output=True, text=True)
            is_active = subprocess.run(["systemctl", "is-active", "zapret_discord_youtube"], capture_output=True, text=True).stdout.strip() == "active"
            if result.stdout.strip() == "enabled" and is_active:
                self.service_enable_switch.select()
            else:
                self.service_enable_switch.deselect()
                if result.stdout.strip() == "enabled" and not is_active:
                    password = self.ask_sudo_password()
                    if password:
                        subprocess.run(["sudo", "-S", "systemctl", "disable", "zapret_discord_youtube"], input=password + "\n", text=True)
                        logger.info("Сервис отключен из-за неактивности")
                        status_label = ctk.CTkLabel(self.main_frame, text="Сервис отключен: неактивен", text_color=COLOR_RED, font=("Inter", 11))
                        status_label.pack(pady=2)
                        self.after(3000, status_label.destroy)
        except Exception as e:
            logger.error(f"Ошибка проверки статуса сервиса: {e}")

    def check_dns_status(self):
        try:
            if os.path.exists("/etc/resolv.conf") and "Generated by NetworkManager" in subprocess.run(["cat", "/etc/resolv.conf"], capture_output=True, text=True).stdout:
                if shutil.which("nmcli"):
                    result = subprocess.run(["nmcli", "con", "show", "--active"], capture_output=True, text=True)
                    active_con = [line for line in result.stdout.splitlines() if "NAME" not in line]
                    if active_con:
                        con_name = active_con[0].split()[0]
                        dns_result = subprocess.run(["nmcli", "con", "show", con_name], capture_output=True, text=True)
                        dns_list = [line for line in dns_result.stdout.splitlines() if "ipv4.dns" in line]
                        if dns_list and any(dns in dns_list[0] for dns in ["176.99.11.77", "80.78.247.254"]):
                            self.dns_switch.select()
                            logger.info("DNS активен через NetworkManager")
                            return
            result = subprocess.run(["grep", "-E", "176.99.11.77|80.78.247.254", "/etc/resolv.conf"], capture_output=True, text=True)
            if result.returncode == 0:
                self.dns_switch.select()
                logger.info("DNS активен в /etc/resolv.conf")
            else:
                self.dns_switch.deselect()
                logger.info("DNS не активен")
        except Exception as e:
            logger.error(f"Ошибка проверки статуса DNS: {e}")
            self.dns_switch.deselect()

    def load_config(self):
        if not os.path.exists(CONF_FILE):
            self.interface_var.set("any")
            self.strategy_var.set("")
            self.dns_switch.deselect()
            self.update_config("initial")
        else:
            try:
                with open(CONF_FILE, "r") as f:
                    lines = f.readlines()
                    for line in lines:
                        line = line.strip()
                        if line.startswith("interface="):
                            interface = line.split("=", 1)[1]
                            self.interface_var.set(interface)
                        elif line.startswith("strategy="):
                            strategy = line.split("=", 1)[1]
                            self.strategy_var.set(strategy)
                        elif line.startswith("dns="):
                            dns_state = line.split("=", 1)[1]
                            if dns_state == "enabled":
                                self.dns_switch.select()
                            elif dns_state == "disabled":
                                self.dns_switch.deselect()
            except Exception as e:
                logger.error(f"Ошибка при чтении {CONF_FILE}: {e}")
        if not self.interface_var.get() and self.interface_combo.cget("values"):
            self.interface_var.set('any')
            self.update_config("interface")
        self.check_dns_status()

    def load_strategies(self):
        logger.info(f"Загрузка стратегий из {REPO_DIR}")
        if self.warning_label:
            self.warning_label.destroy()
            self.warning_label = None
        if not os.path.exists(REPO_DIR):
            logger.error(f"Каталог {REPO_DIR} не найден")
            self.warning_label = ctk.CTkLabel(self.main_frame, text="Каталог zapret-latest не найден!", text_color=COLOR_RED, font=("Inter", 11))
            self.warning_label.pack(pady=2)
            self.strategy_combo.configure(values=[])
            self.strategy_var.set("")
            self.session_button.configure(state="disabled")
            self.service_enable_switch.configure(state="disabled")
            self.update_config("strategy")
            return
        try:
            strategies = [f for f in os.listdir(REPO_DIR) if f.endswith(".bat") and os.access(os.path.join(REPO_DIR, f), os.R_OK)]
            logger.info(f"Все файлы в {REPO_DIR}: {os.listdir(REPO_DIR)}")
            logger.info(f"Найдены доступные .bat файлы: {strategies}")
            if not strategies:
                logger.error(f"Не найдены .bat файлы в {REPO_DIR}")
                self.warning_label = ctk.CTkLabel(self.main_frame, text="Файлы стратегий не найдены!", text_color=COLOR_RED, font=("Inter", 11))
                self.warning_label.pack(pady=2)
                self.strategy_combo.configure(values=[])
                self.strategy_var.set("")
                self.session_button.configure(state="disabled")
                self.service_enable_switch.configure(state="disabled")
            else:
                self.strategy_combo.configure(values=strategies)
                self.strategy_combo.update()  # Force GUI update
                if not self.strategy_var.get() or self.strategy_var.get() not in strategies:
                    self.strategy_var.set(strategies[0])
                    logger.info(f"Установлена стратегия по умолчанию: {self.strategy_var.get()}")
                self.session_button.configure(state="normal")
                self.service_enable_switch.configure(state="normal")
            self.update_config("strategy")
        except Exception as e:
            logger.error(f"Ошибка загрузки стратегий: {e}")
            self.warning_label = ctk.CTkLabel(self.main_frame, text="Ошибка загрузки стратегий!", text_color=COLOR_RED, font=("Inter", 11))
            self.warning_label.pack(pady=2)
            self.after(3000, self.warning_label.destroy)

    def update_config(self, source="unknown"):
        interface = self.interface_var.get() or "any"
        strategy = self.strategy_var.get() or ""
        auto_update = "false"
        dns_state = "enabled" if self.dns_switch.get() else "disabled"
        logger.info(f"update_config от {source}: interface='{interface}', strategy='{strategy}', auto_update={auto_update}, dns={dns_state}")
        try:
            with open(CONF_FILE, "w") as f:
                f.write(f"interface={interface}\n")
                f.write(f"auto_update={auto_update}\n")
                f.write(f"strategy={strategy}\n")
                f.write(f"dns={dns_state}\n")
            logger.info(f"conf.env создан/обновлён: {CONF_FILE}")
            status_label = ctk.CTkLabel(self.main_frame, text=f"Конфигурация сохранена ({source})", text_color=COLOR_GREEN, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(2000, status_label.destroy)
        except Exception as e:
            logger.error(f"Ошибка записи {CONF_FILE}: {e}")
            status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)

    def ask_sudo_password(self):
        if self.sudo_password:
            return self.sudo_password
        dialog = SudoPasswordDialog(self)
        self.wait_window(dialog)
        self.sudo_password = dialog.password
        return self.sudo_password

    def toggle_session(self):
        self.session_button.configure(state="disabled")
        self.update()
        if self.session_button.text == "▶ Пуск":
            self.load_strategies()
            if self.interface_var.get() == "" or self.strategy_var.get() == "":
                logger.error(f"Не выбраны интерфейс или стратегия: interface={self.interface_var.get()}, strategy={self.strategy_var.get()}")
                status_label = ctk.CTkLabel(self.main_frame, text="Выберите интерфейс и стратегию!", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.session_button.configure(state="normal")
                self.update()
                return
            if not os.path.exists(MAIN_SCRIPT):
                logger.error(f"Скрипт не найден: {MAIN_SCRIPT}")
                status_label = ctk.CTkLabel(self.main_frame, text="Скрипт сессии не найден!", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.session_button.configure(state="normal")
                self.update()
                return
            if not os.path.exists(os.path.join(REPO_DIR, self.strategy_var.get())):
                logger.error(f"Файл стратегии не найден: {self.strategy_var.get()}")
                status_label = ctk.CTkLabel(self.main_frame, text=f"Файл стратегии {self.strategy_var.get()} не найден!", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.session_button.configure(state="normal")
                self.update()
                return
            password = self.ask_sudo_password()
            if not password:
                logger.error("Пароль sudo не предоставлен")
                self.session_button.configure(state="normal")
                self.update()
                return
            try:
                subprocess.run(["sudo", "-S", "pkill", "-f", "nfqws"], input=password + "\n", text=True, capture_output=True)
                if os.path.exists(STOP_SCRIPT):
                    subprocess.run(["sudo", "-S", STOP_SCRIPT], input=password + "\n", text=True, capture_output=True)
                self.session_process = subprocess.Popen(
                    ["sudo", "-S", MAIN_SCRIPT, "-nointeractive"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                self.session_process.stdin.write(password + "\n")
                self.session_process.stdin.flush()
                time.sleep(1)
                logger.info(f"Сессия запущена с interface={self.interface_var.get()}, strategy={self.strategy_var.get()}")
                status_label = ctk.CTkLabel(self.main_frame, text="Сессия запущена", text_color=COLOR_GREEN, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(2000, status_label.destroy)
                self.session_button.configure(text="⏹ Стоп", fg_color=COLOR_RED, state="normal")
                self.update()
            except Exception as e:
                logger.error(f"Ошибка запуска сессии: {e}")
                self.session_process = None
                status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка запуска сессии: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.session_button.configure(state="normal")
                self.update()
        else:
            password = self.ask_sudo_password()
            if not password:
                self.session_button.configure(state="normal")
                self.update()
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
            except Exception as e:
                logger.error(f"Ошибка остановки сессии: {e}")
                self.session_process = None
                status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка остановки сессии: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.session_button.configure(text="▶ Пуск", fg_color=COLOR_GREEN, state="normal")
                self.update()
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
            return
        if self.service_enable_switch.get():
            password = self.ask_sudo_password()
            if not password:
                self.service_enable_switch.deselect()
                self.update()
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
            except Exception as e:
                logger.error(f"Ошибка запуска сервиса: {e}")
                self.service_enable_switch.deselect()
                status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка запуска сервиса: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.update()
        else:
            password = self.ask_sudo_password()
            if not password:
                self.service_enable_switch.select()
                self.update()
                return
            try:
                subprocess.run(["sudo", "-S", "systemctl", "disable", "--now", "zapret_discord_youtube"], input=password + "\n", text=True, check=True)
                logger.info("Сервис остановлен")
                status_label = ctk.CTkLabel(self.main_frame, text="Сервис остановлен", text_color=COLOR_GREEN, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(2000, status_label.destroy)
                self.check_session_status()
                self.update()
            except Exception as e:
                logger.error(f"Ошибка остановки сервиса: {e}")
                self.service_enable_switch.select()
                status_label = ctk.CTkLabel(self.main_frame, text=f"Ошибка остановки сервиса: {str(e)[:50]}...", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.update()

    def toggle_dns(self):
        if not os.path.exists(DNS_SCRIPT):
            logger.error(f"Скрипт DNS не найден: {DNS_SCRIPT}")
            self.dns_switch.deselect()
            status_label = ctk.CTkLabel(self.main_frame, text="Скрипт DNS не найден!", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
            self.update()
            return
        if not os.access(DNS_SCRIPT, os.X_OK):
            logger.error(f"Скрипт DNS не имеет прав на выполнение: {DNS_SCRIPT}")
            self.dns_switch.deselect()
            status_label = ctk.CTkLabel(self.main_frame, text="Скрипт DNS не исполняемый!", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
            self.update()
            return
        password = self.ask_sudo_password()
        if not password:
            logger.error("Пароль sudo не предоставлен")
            if self.dns_switch.get():
                self.dns_switch.deselect()
            else:
                self.dns_switch.select()
            status_label = ctk.CTkLabel(self.main_frame, text="Пароль sudo не предоставлен!", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
            self.update()
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

    def check_update(self):
        logger.info("Проверка обновлений")
        try:
            response = requests.get("https://api.github.com/repos/Flowseal/zapret-discord-youtube/releases/latest", timeout=5)
            response.raise_for_status()
            latest_version = response.json().get("tag_name", "").lstrip("v")
            try:
                parsed_latest = version.parse(latest_version)
                current_version = self.load_version()
                parsed_current = version.parse(current_version)
            except version.InvalidVersion:
                logger.error(f"Недопустимый формат версии: текущая={current_version}, последняя={latest_version}")
                status_label = ctk.CTkLabel(self.main_frame, text="Ошибка: неверный формат версии", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
                self.update()
                return
            if parsed_latest > parsed_current:
                logger.info(f"Обнаружена новая версия: {latest_version}, текущая версия: {current_version}")
                status_label = ctk.CTkLabel(self.main_frame, text="Вышла новая версия, обновитесь!", text_color=COLOR_RED, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(3000, status_label.destroy)
            else:
                logger.info(f"Текущая версия актуальна: {current_version}")
                status_label = ctk.CTkLabel(self.main_frame, text="Установлена последняя версия", text_color=COLOR_GREEN, font=("Inter", 11))
                status_label.pack(pady=2)
                self.after(2000, status_label.destroy)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.error(f"Репозиторий или релизы не найдены: {e}")
                status_label = ctk.CTkLabel(self.main_frame, text="Репозиторий или релизы недоступны", text_color=COLOR_RED, font=("Inter", 11))
            else:
                logger.error(f"Ошибка HTTP при проверке обновления: {e}")
                status_label = ctk.CTkLabel(self.main_frame, text="Новой версии нет", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при проверке обновления: {e}")
            status_label = ctk.CTkLabel(self.main_frame, text="Ошибка сети при проверке обновления", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
        except Exception as e:
            logger.error(f"Неизвестная ошибка при проверке обновления: {e}")
            status_label = ctk.CTkLabel(self.main_frame, text="Неизвестная ошибка", text_color=COLOR_RED, font=("Inter", 11))
            status_label.pack(pady=2)
            self.after(3000, status_label.destroy)
        self.update()

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