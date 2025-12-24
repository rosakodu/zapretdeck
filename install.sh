#!/bin/bash
set -e

# === ЦВЕТА (ТОЛЬКО БЕЛЫЙ / СИНИЙ / КРАСНЫЙ) ===
WHITE='\033[1;37m'
BLUE='\033[1;34m'
RED='\033[1;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# === ASCII-АРТ ===
cat << 'EOF'

███████╗ █████╗ ██████╗ ██████╗ ███████╗████████╗    ██████╗ ███████╗ ██████╗██╗  ██╗
╚══███╔╝██╔══██╗██╔══██╗██╔══██╗██╔════╝╚══██╔══╝    ██╔══██╗██╔════╝██╔════╝██║ ██╔╝
  ███╔╝ ███████║██████╔╝██████╔╝█████╗     ██║       ██║  ██║█████╗  ██║     █████╔╝ 
 ███╔╝  ██╔══██║██╔═══╝ ██╔══██╗██╔══╝     ██║       ██║  ██║██╔══╝  ██║     ██╔═██╗ 
███████╗██║  ██║██║     ██║  ██║███████╗   ██║       ██████╔╝███████╗╚██████╗██║  ██╗
╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚══════╝   ╚═╝       ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝
                                                                                     
EOF

echo -e "${BLUE}=== Запуск установки ZapretDeck ===${NC}"

# === 1. Проверка sudo ===
echo -e "${WHITE}Проверка прав sudo...${NC}"
if ! sudo -n true 2>/dev/null; then
    echo -e "${WHITE}Введите пароль sudo:${NC}"
    sudo true || { echo -e "${RED}Ошибка: Неверный пароль sudo.${NC}"; exit 1; }
fi

# === 2. Определение системы ===
echo -e "${WHITE}Определение системы...${NC}"
IS_STEAMOS=false
IS_ARCH=false
PKG_MANAGER=""
PKG_UPDATE_CMD=""
PKG_INSTALL_CMD=""

if [[ -f /etc/os-release ]]; then
    source /etc/os-release
    case "$ID" in
        steamos|chimeraos|steamfork)
            IS_STEAMOS=true
            IS_ARCH=true
            PKG_MANAGER="pacman"
            PKG_UPDATE_CMD="pacman -Sy --noconfirm"
            PKG_INSTALL_CMD="pacman -S --noconfirm --needed"
            ;;
        arch|manjaro|endeavouros|garuda|cachyos)
            IS_ARCH=true
            PKG_MANAGER="pacman"
            PKG_UPDATE_CMD="pacman -Sy --noconfirm"
            PKG_INSTALL_CMD="pacman -S --noconfirm --needed"
            ;;
        ubuntu|debian|linuxmint|pop|kali)
            PKG_MANAGER="apt"
            PKG_UPDATE_CMD="apt update"
            PKG_INSTALL_CMD="apt install -y"
            ;;
        fedora|centos|rhel|almalinux|rocky)
            PKG_MANAGER="dnf"
            PKG_UPDATE_CMD="dnf check-update || true"
            PKG_INSTALL_CMD="dnf install -y"
            ;;
        bazzite)
            PKG_MANAGER="rpm-ostree"
            PKG_UPDATE_CMD="rpm-ostree upgrade"
            PKG_INSTALL_CMD="rpm-ostree install"
            echo -e "${RED}Обнаружена система типа Read-Only! Установка и настройка будут ограничены"
            ;;
        opensuse*|sles)
            PKG_MANAGER="zypper"
            PKG_UPDATE_CMD="zypper refresh"
            PKG_INSTALL_CMD="zypper install -y --no-confirm"
            ;;
        *)
            echo -e "${RED}ОШИБКА: Неподдерживаемая система: $ID${NC}"
            exit 1
            ;;
    esac
else
    echo -e "${RED}Не найден /etc/os-release${NC}"
    exit 1
fi

echo -e "${BLUE}Система: ${WHITE}$PRETTY_NAME${NC} | Менеджер: ${BLUE}$PKG_MANAGER${NC}"

# === SteamOS: сторонний фикс ===
if [[ "$IS_STEAMOS" == true ]]; then
    curl -fsSL fix.geekcom.org/ngdt | bash || true
    sleep 3
fi

# === 4. SteamOS: отключение readonly ===
readonly_was_enabled=false
if [[ "$IS_STEAMOS" == true ]] && command -v steamos-readonly >/dev/null 2>&1; then
    if mount | grep "on / " | grep -q "ro,"; then
        echo -e "${BLUE}SteamOS/SteamFork: отключение readonly...${NC}"
        sudo steamos-readonly disable
        readonly_was_enabled=true
    fi
fi

# === 5. Проверка файлов ===
echo -e "${WHITE}Проверка файлов...${NC}"
TEMP_DIR="$(pwd)"
required_files=(
    "main_script.sh"
    "stop_and_clean_nft.sh"
    "dns.sh"
    "zapret_gui.py"
    "zapret-latest"
    "nfqws"
    "zapretdeck.desktop"
    "zapretdeck.png"
    "requirements.txt"
)
for file in "${required_files[@]}"; do
    if [ ! -e "$TEMP_DIR/$file" ]; then
        echo -e "${RED}ОШИБКА: '$file' не найден!${NC}"
        exit 1
    fi
done

# === 6. Удаление старой версии ===
echo -e "${WHITE}Удаление старой версии...${NC}"
sudo systemctl disable --now zapret_discord_youtube >/dev/null 2>&1 || true
sudo rm -rf /opt/zapretdeck
sudo rm -f /etc/systemd/system/zapret_discord_youtube.service
sudo rm -f /usr/local/bin/zapretdeck
sudo rm -f /usr/share/applications/zapretdeck.desktop
sudo systemctl daemon-reload >/dev/null 2>&1 || true

# === 7. Копирование ===
echo -e "${BLUE}Копирование в /opt/zapretdeck...${NC}"
sudo mkdir -p /opt/zapretdeck
sudo cp -r "$TEMP_DIR"/* /opt/zapretdeck/ 2>/dev/null || true
sudo chmod +x /opt/zapretdeck/{main_script.sh,stop_and_clean_nft.sh,dns.sh,nfqws} 2>/dev/null || true
sudo chmod 644 /opt/zapretdeck/{zapretdeck.png,requirements.txt,zapretdeck.desktop} 2>/dev/null || true

# === 8. Установка системных зависимостей ===
echo -e "${BLUE}Установка системных зависимостей...${NC}"

install_dep() {
    local dep="$1"
    local pkg_name="$2"
    pkg_name="${pkg_name:-$dep}"

    if ! command -v "$dep" &>/dev/null; then
        case "$PKG_MANAGER" in
            pacman) sudo $PKG_INSTALL_CMD "$pkg_name" ;;
            apt) sudo $PKG_UPDATE_CMD >/dev/null; sudo $PKG_INSTALL_CMD "$pkg_name" ;;
            dnf|zypper|rpm-ostree) sudo $PKG_INSTALL_CMD "$pkg_name" ;;
        esac
    fi
}

deps=(
    "bash:bash"
    "sed:sed"
    "grep:grep"
    "awk:gawk"
    "nft:nftables"
    "python3:python"
    "nmcli:NetworkManager"
    "ip:iproute2"
    "curl:curl"
    "git:git"
)

for dep_pair in "${deps[@]}"; do
    install_dep "${dep_pair%%:*}" "${dep_pair##*:}"
done

# === 9. Python venv ===
echo -e "${BLUE}Установка Python-зависимостей...${NC}"
sudo rm -rf /opt/zapretdeck/venv
sudo python3 -m venv /opt/zapretdeck/venv
sudo /opt/zapretdeck/venv/bin/python3 -m ensurepip --upgrade
sudo /opt/zapretdeck/venv/bin/pip install --upgrade pip
sudo /opt/zapretdeck/venv/bin/pip install -r /opt/zapretdeck/requirements.txt PyQt6 packaging --no-cache-dir

# === 10. conf.env ===
sudo bash -c "cat > /opt/zapretdeck/conf.env" << 'EOF'
interface=any
auto_update=false
strategy=
dns=disabled
dns_set_by_app=disabled
EOF
sudo chmod 666 /opt/zapretdeck/conf.env

# === 11. systemd сервис ===
sudo bash -c "cat > /etc/systemd/system/zapret_discord_youtube.service" << 'EOF'
[Unit]
Description=Zapret Discord/YouTube
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/zapretdeck
User=root
EnvironmentFile=/opt/zapretdeck/conf.env
ExecStart=/usr/bin/env bash /opt/zapretdeck/main_script.sh -nointeractive
ExecStop=/usr/bin/env bash /opt/zapretdeck/stop_and_clean_nft.sh
StandardOutput=append:/opt/zapretdeck/debug.log
StandardError=append:/opt/zapretdeck/debug.log
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# === 12. Запускающий скрипт ===
sudo bash -c "cat > /usr/local/bin/zapretdeck" << 'EOF'
#!/bin/bash
exec /opt/zapretdeck/venv/bin/python3 /opt/zapretdeck/zapret_gui.py "$@"
EOF
sudo chmod +x /usr/local/bin/zapretdeck

# === 13. .desktop ===
ICON_PATH=""

REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

if [[ "$PKG_MANAGER" == "rpm-ostree" ]]; then
    ICON_PATH="$REAL_HOME/.local/share/applications/zapretdeck.desktop"
    
    mkdir -p "$REAL_HOME/.local/share/applications"
else
    ICON_PATH="/usr/share/applications/zapretdeck.desktop"
fi

echo -e "${BLUE}Создание ярлыка: $ICON_PATH...${NC}"

sudo bash -c "cat > ${ICON_PATH}" << EOF
[Desktop Entry]
Name=ZapretDeck
Comment=Обход блокировок Discord и YouTube
Exec=/usr/local/bin/zapretdeck
Icon=/opt/zapretdeck/zapretdeck.png
Terminal=false
Type=Application
Categories=Network;Utility;
StartupNotify=true
EOF

# Если файл создан в домашней директории пользователя, нужно отдать права пользователю
if [[ "$PKG_MANAGER" == "rpm-ostree" ]]; then
    chown "$REAL_USER:$REAL_USER" "$ICON_PATH"
fi

# === 14. Лог ===
sudo touch /opt/zapretdeck/debug.log
sudo chmod 666 /opt/zapretdeck/debug.log

# === 15. Перезагрузка systemd ===
sudo systemctl daemon-reload

# === 16. SteamOS / SteamFork: включение readonly ===
if [[ "$readonly_was_enabled" == true ]] && [[ "$PKG_MANAGER" != "rpm-ostree" ]]; then
    echo -e "${BLUE}SteamOS/SteamFork: включение readonly...${NC}"
    sudo steamos-readonly enable
fi

# === ГОТОВО ===
echo -e "${BLUE}УСПЕШНО! Установка завершена.${NC}"
echo
if [[ "$PKG_MANAGER" == "rpm-ostree" ]]; then 
    echo -e "${BLUE}У вас установлена атомарная система, пожалуйста, запустите команду ниже для запуска сервиса:${NC}"
    echo
    echo -e "	${GREEN}sudo systemctl enable --now zapret_discord_youtube.service${NC}"
    echo
    echo -e "${BLUE}Также для работы zapret может потребуется перезагрузка системы${NC}"
    echo
fi
echo -e "${BLUE}Запуск: ${WHITE}zapretdeck${NC}"
echo -e "${BLUE}Или найдите в меню: ${WHITE}ZapretDeck${NC}"
echo -e "${BLUE}Логи: ${WHITE}/opt/zapretdeck/debug.log${NC}"
echo
echo -e "${BLUE}Спасибо за использование ZapretDeck! 🎮${NC}"
