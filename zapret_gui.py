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

# Логирование
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

# Цвета
COLOR_BG = "#242424"
COLOR_ACCENT = "#0078D4"
COLOR_GREEN = "#107C10"
COLOR_RED = "#C50F1F"
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
        self.geometry("650x650")
        self.minsize(650, 650)
        self.maxsize(650, 650)
        self.session_process = None
        self.sudo_password = None
        self.configure(fg_color=COLOR_BG)
        self.warning_label = None
        icon_path = os.path.join(BASE_DIR, "zapretdeck.png")
        if os.path.exists(icon_path):
            icon = PhotoImage(file=icon_path)
            self.wm_iconphoto(True, icon)
        self.protocol("WM_DELETE_WINDOW", self.on_exit)

        if not self.check_dependencies():
            logger.error("Завершение из-за отсутствия зависимостей")
            self.quit()
            return

        self.loading_label = ctk.CTkLabel(self, text="Загрузка...", font=("Inter", 12), text_color=COLOR_WHITE)
        self.loading_label.pack(pady=10)
        self.update()
        self.after(100, self.setup_ui)
        self.after(1000, self.check_session_status)

    def setup_ui(self):
        self.loading_label.destroy()
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
        self.session_button = RoundButton(button_container, text="Пуск", command=self.toggle_session,
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

        # Изменено: "Cloudflare" вместо "Cloudflare 1.1.1.1"
        self.cloudflare_dns_switch = ctk.CTkSwitch(switch_frame, text="Cloudflare", command=self.toggle_cloudflare_dns,
                                                   font=("Inter", 11), width=220, height=30,
                                                   progress_color=COLOR_ACCENT)
        self.cloudflare_dns_switch.pack(anchor="w", pady=2)

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
        return "0.0.4"

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
            if is_running and self.session_button.text != "Стоп":
                logger.info("Обнаружены процессы nfqws")
                self.session_button.configure(text="Стоп", fg_color=COLOR_RED)
            elif not is_running and self.session_button.text != "Пуск":
                logger.info("Процессы nfqws не найдены")
                self.session_process = None
                self.session_button.configure(text="Пуск", fg_color=COLOR_GREEN)
            self.after(1000, self.check_session_status)
        except Exception as e:
            logger.error(f"Ошибка проверки сессии: {e}")

    def check_service_status(self):
        try:
            result = subprocess.run(["systemctl", "is-enabled", "zapret_discord_youtube"], capture_output=True, text=True)
            is_active = subprocess.run(["systemctl", "is-active", "zapret_discord_youtube"], capture_output=True, text=True).stdout.strip() == "active"
            if result.stdout.strip() == "enabled" and is_active:
                self.service_enable_switch.select()
            else:
                self.service_enable_switch.deselect()
        except Exception as e:
            logger.error(f"Ошибка проверки сервиса: {e}")

    def check_dns_status(self):
        try:
            if not os.path.exists("/etc/resolv.conf"):
                self.dns_switch.deselect()
                self.cloudflare_dns_switch.deselect()
                return

            with open("/etc/resolv.conf", "r") as f:
                content = f.read()

            # NetworkManager
            if "Generated by NetworkManager" in content and shutil.which("nmcli"):
                result = subprocess.run(["nmcli", "con", "show", "--active"], capture_output=True, text=True)
                active_con = [line for line in result.stdout.splitlines() if "NAME" not in line]
                if active_con:
                    con_name = active_con[0].split()[0]
                    dns_result = subprocess.run(["nmcli", "con", "show", con_name], capture_output=True, text=True)
                    dns_lines = [line for line in dns_result.stdout.splitlines() if "ipv4.dns" in line]
                    if dns_lines:
                        dns_values = dns_lines[0].split(":", 1)[1].strip()
                        if any(ip in dns_values for ip in ["176.99.11.77", "80.78.247.254"]):
                            self.dns_switch.select()
                            self.cloudflare_dns_switch.deselect()
                            return
                        elif any(ip in dns_values for ip in ["1.1.1.1", "1.0.0.1"]):
                            self.cloudflare_dns_switch.select()
                            self.dns_switch.deselect()
                            return

            # Прямой resolv.conf
            if any(ip in content for ip in ["176.99.11.77", "80.78.247.254"]):
                self.dns_switch.select()
                self.cloudflare_dns_switch.deselect()
            elif any(ip in content for ip in ["1.1.1.1", "1.0.0.1"]):
                self.cloudflare_dns_switch.select()
                self.dns_switch.deselect()
            else:
                self.dns_switch.deselect()
                self.cloudflare_dns_switch.deselect()
        except Exception as e:
            logger.error(f"Ошибка проверки DNS: {e}")
            self.dns_switch.deselect()
            self.cloudflare_dns_switch.deselect()

    def load_config(self):
        if not os.path.exists(CONF_FILE):
            self.interface_var.set("any")
            self.strategy_var.set("")
            self.dns_switch.deselect()
            self.cloudflare_dns_switch.deselect()
            self.update_config("initial")
        else:
            try:
                with open(CONF_FILE, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("interface="):
                            self.interface_var.set(line.split("=", 1)[1])
                        elif line.startswith("strategy="):
                            self.strategy_var.set(line.split("=", 1)[1])
                        elif line.startswith("dns_provider="):
                            provider = line.split("=", 1)[1]
                            if provider == "xbox":
                                self.dns_switch.select()
                                self.cloudflare_dns_switch.deselect()
                            elif provider == "cloudflare":
                                self.cloudflare_dns_switch.select()
                                self.dns_switch.deselect()
                            else:
                                self.dns_switch.deselect()
                                self.cloudflare_dns_switch.deselect()
            except Exception as e:
                logger.error(f"Ошибка чтения {CONF_FILE}: {e}")
        if not self.interface_var.get():
            self.interface_var.set('any')
            self.update_config("interface")
        self.check_dns_status()

    def load_strategies(self):
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
            return
        try:
            strategies = [f for f in os.listdir(REPO_DIR) if f.endswith(".bat") and os.access(os.path.join(REPO_DIR, f), os.R_OK)]
            if not strategies:
                self.warning_label = ctk.CTkLabel(self.main_frame, text="Файлы стратегий не найдены!", text_color=COLOR_RED, font=("Inter", 11))
                self.warning_label.pack(pady=2)
                self.strategy_combo.configure(values=[])
                self.strategy_var.set("")
                self.session_button.configure(state="disabled")
                self.service_enable_switch.configure(state="disabled")
            else:
                self.strategy_combo.configure(values=strategies)
                if not self.strategy_var.get() or self.strategy_var.get() not in strategies:
                    self.strategy_var.set(strategies[0])
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

        if self.dns_switch.get():
            dns_provider = "xbox"
        elif self.cloudflare_dns_switch.get():
            dns_provider = "cloudflare"
        else:
            dns_provider = "disabled"

        logger.info(f"update_config: dns_provider={dns_provider}")
        try:
            with open(CONF_FILE, "w") as f:
                f.write(f"interface={interface}\n")
                f.write(f"auto_update={auto_update}\n")
                f.write(f"strategy={strategy}\n")
                f.write(f"dns_provider={dns_provider}\n")
            self._show_status("Конфигурация сохранена", COLOR_GREEN)
        except Exception as e:
            logger.error(f"Ошибка записи {CONF_FILE}: {e}")
            self._show_status(f"Ошибка: {str(e)[:50]}...", COLOR_RED)

    def ask_sudo_password(self):
        if self.sudo_password:
            return self.sudo_password
        dialog = SudoPasswordDialog(self)
        self.wait_window(dialog)
        self.sudo_password = dialog.password
        return self.sudo_password

    def toggle_dns(self):
        if self.dns_switch.get():
            if self.cloudflare_dns_switch.get():
                self.cloudflare_dns_switch.deselect()
            self._apply_dns("xbox")
        else:
            if not self.cloudflare_dns_switch.get():
                self._apply_dns("unset")
            else:
                self.update_config("dns")

    def toggle_cloudflare_dns(self):
        if self.cloudflare_dns_switch.get():
            if self.dns_switch.get():
                self.dns_switch.deselect()
            self._apply_dns("cloudflare")
        else:
            if not self.dns_switch.get():
                self._apply_dns("unset")
            else:
                self.update_config("dns")

    def _apply_dns(self, action):
        if not os.path.exists(DNS_SCRIPT):
            logger.error(f"Скрипт DNS не найден: {DNS_SCRIPT}")
            self.dns_switch.deselect()
            self.cloudflare_dns_switch.deselect()
            self._show_status("Скрипт DNS не найден!", COLOR_RED)
            return

        if not os.access(DNS_SCRIPT, os.X_OK):
            logger.error(f"Скрипт DNS не исполняемый: {DNS_SCRIPT}")
            self.dns_switch.deselect()
            self.cloudflare_dns_switch.deselect()
            self._show_status("Скрипт DNS не исполняемый!", COLOR_RED)
            return

        password = self.ask_sudo_password()
        if not password:
            self.dns_switch.deselect()
            self.cloudflare_dns_switch.deselect()
            self.update()
            return

        try:
            if action == "unset":
                cmd = ["sudo", "-S", DNS_SCRIPT, "unset"]
                text = "DNS отключён"
            else:
                cmd = ["sudo", "-S", DNS_SCRIPT, "set", action]
                provider = "xbox-dns.ru" if action == "xbox" else "Cloudflare"
                text = f"{provider} DNS включён"

            result = subprocess.run(cmd, input=password + "\n", text=True, capture_output=True, check=True)
            logger.info(f"DNS {action}: {result.stdout.strip()}")

            self.check_dns_status()
            self.update_config("dns")
            self._show_status(text, COLOR_GREEN)

        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка DNS: {e.stderr}")
            self.check_dns_status()
            self._show_status(f"Ошибка DNS: {e.stderr[:50]}...", COLOR_RED)
        except Exception as e:
            logger.error(f"Неизвестная ошибка DNS: {e}")
            self.check_dns_status()
            self._show_status(f"Ошибка: {str(e)[:50]}...", COLOR_RED)
        self.update()

    def _show_status(self, text, color, timeout=2500):
        status_label = ctk.CTkLabel(self.main_frame, text=text, text_color=color, font=("Inter", 11))
        status_label.pack(pady=2)
        self.after(timeout, status_label.destroy)

    def toggle_session(self):
        self.session_button.configure(state="disabled")
        self.update()
        if self.session_button.text == "Пуск":
            self.load_strategies()
            if not self.interface_var.get() or not self.strategy_var.get():
                self._show_status("Выберите интерфейс и стратегию!", COLOR_RED)
                self.session_button.configure(state="normal")
                return
            if not os.path.exists(MAIN_SCRIPT):
                self._show_status("Скрипт сессии не найден!", COLOR_RED)
                self.session_button.configure(state="normal")
                return
            if not os.path.exists(os.path.join(REPO_DIR, self.strategy_var.get())):
                self._show_status("Файл стратегии не найден!", COLOR_RED)
                self.session_button.configure(state="normal")
                return
            password = self.ask_sudo_password()
            if not password:
                self.session_button.configure(state="normal")
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
                self._show_status("Сессия запущена", COLOR_GREEN)
                self.session_button.configure(text="Стоп", fg_color=COLOR_RED, state="normal")
            except Exception as e:
                logger.error(f"Ошибка запуска: {e}")
                self._show_status(f"Ошибка: {str(e)[:50]}...", COLOR_RED)
                self.session_button.configure(state="normal")
        else:
            password = self.ask_sudo_password()
            if not password:
                self.session_button.configure(state="normal")
                return
            try:
                subprocess.run(["sudo", "-S", "nft", "flush", "ruleset"], input=password + "\n", text=True, capture_output=True, check=True)
                subprocess.run(["sudo", "-S", "pkill", "-f", "nfqws"], input=password + "\n", text=True, capture_output=True)
                if self.session_process:
                    self.session_process.terminate()
                    self.session_process.wait(timeout=10)
                self.session_process = None
                time.sleep(1)
                self._show_status("Сессия остановлена", COLOR_GREEN)
                self.session_button.configure(text="Пуск", fg_color=COLOR_GREEN, state="normal")
            except Exception as e:
                logger.error(f"Ошибка остановки: {e}")
                self._show_status(f"Ошибка: {str(e)[:50]}...", COLOR_RED)
                self.session_button.configure(text="Пуск", fg_color=COLOR_GREEN, state="normal")
        self.check_session_status()

    def create_systemd_service(self):
        if not os.path.exists(MAIN_SCRIPT) or not os.path.exists(STOP_SCRIPT):
            self._show_status("Скрипты сервиса не найдены!", COLOR_RED)
            return
        if not self.strategy_var.get() or not os.path.exists(os.path.join(REPO_DIR, self.strategy_var.get())):
            self._show_status("Выберите стратегию!", COLOR_RED)
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
            self._show_status(f"Ошибка: {str(e)[:50]}...", COLOR_RED)

    def toggle_service(self):
        if not self.interface_var.get() or not self.strategy_var.get():
            self._show_status("Выберите интерфейс и стратегию!", COLOR_RED)
            self.service_enable_switch.deselect()
            return
        if self.service_enable_switch.get():
            password = self.ask_sudo_password()
            if not password:
                self.service_enable_switch.deselect()
                return
            try:
                result = subprocess.run(["systemctl", "cat", "zapret_discord_youtube"], capture_output=True, text=True)
                if result.returncode != 0 or not os.path.exists(os.path.join(REPO_DIR, self.strategy_var.get())):
                    self.create_systemd_service()
                subprocess.run(["sudo", "-S", "systemctl", "enable", "--now", "zapret_discord_youtube"], input=password + "\n", text=True, check=True)
                self._show_status("Сервис запущен", COLOR_GREEN)
            except Exception as e:
                logger.error(f"Ошибка запуска сервиса: {e}")
                self.service_enable_switch.deselect()
                self._show_status(f"Ошибка: {str(e)[:50]}...", COLOR_RED)
        else:
            password = self.ask_sudo_password()
            if not password:
                self.service_enable_switch.select()
                return
            try:
                subprocess.run(["sudo", "-S", "systemctl", "disable", "--now", "zapret_discord_youtube"], input=password + "\n", text=True, check=True)
                self._show_status("Сервис остановлен", COLOR_GREEN)
            except Exception as e:
                logger.error(f"Ошибка остановки сервиса: {e}")
                self.service_enable_switch.select()
                self._show_status(f"Ошибка: {str(e)[:50]}...", COLOR_RED)
        self.check_session_status()

    def check_update(self):
        logger.info("Проверка обновлений")
        try:
            response = requests.get("https://api.github.com/repos/Flowseal/zapret-discord-youtube/releases/latest", timeout=5)
            response.raise_for_status()
            latest = response.json().get("tag_name", "").lstrip("v")
            current = self.load_version()
            if version.parse(latest) > version.parse(current):
                self._show_status("Вышла новая версия!", COLOR_RED)
            else:
                self._show_status("Последняя версия", COLOR_GREEN)
        except Exception as e:
            logger.error(f"Ошибка обновления: {e}")
            self._show_status("Ошибка сети", COLOR_RED)

    def on_exit(self):
        if self.session_button.text == "Стоп" and not self.service_enable_switch.get():
            if messagebox.askyesno("Подтверждение", "Сессия активна. Продолжить в фоне?"):
                self.session_process = None
            else:
                password = self.ask_sudo_password()
                if password:
                    try:
                        subprocess.run(["sudo", "-S", "nft", "flush", "ruleset"], input=password + "\n", text=True, capture_output=True, check=True)
                        subprocess.run(["sudo", "-S", "pkill", "-f", "nfqws"], input=password + "\n", text=True, capture_output=True)
                        if self.session_process:
                            self.session_process.terminate()
                            self.session_process.wait(timeout=10)
                    except Exception as e:
                        logger.error(f"Ошибка остановки: {e}")
                self.session_process = None
        self.sudo_password = None
        self.quit()

if __name__ == "__main__":
    try:
        app = ZapretGUI()
        app.mainloop()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise
