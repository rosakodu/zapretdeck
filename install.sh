#!/bin/bash
set -e

# === ЦВЕТА ===
WHITE='\033[1;37m'
BLUE='\033[1;34m'
RED='\033[1;31m'
GREEN='\033[1;32m'
NC='\033[0m'

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
echo

# === 0. Функция Да / Нет для фиксов ===
ask_yes_no() {
    local question="$1"
    local default="$2"   # y / n

    local prompt
    if [[ "$default" == "y" ]]; then
        prompt="[Y/n]"
    else
        prompt="[y/N]"
    fi

    while true; do
        echo -ne "${WHITE}${question} ${prompt}: ${NC}"
        read -r answer
        answer="${answer,,}"

        [[ -z "$answer" ]] && answer="$default"

        case "$answer" in
            y|yes) return 0 ;;
            n|no)  return 1 ;;
            *) echo -e "${RED}Введите y или n${NC}" ;;
        esac
    done
}

# === 1. Проверка sudo ===
echo -e "${WHITE}Проверка прав sudo...${NC}"
if ! sudo -n true 2>/dev/null; then
    echo -e "${WHITE}Введите пароль sudo для установки:${NC}"
    sudo true || { echo -e "${RED}Ошибка: Неверный пароль sudo.${NC}"; exit 1; }
fi

# === 2. Определение системы ===
echo -e "${WHITE}Определение системы...${NC}"
IS_STEAMOS=false
PKG_MANAGER=""
PKG_UPDATE_CMD=""
PKG_INSTALL_CMD=""

if [[ -f /etc/os-release ]]; then
    source /etc/os-release
    case "$ID" in
        steamos|chimeraos|steamfork)
            IS_STEAMOS=true
            PKG_MANAGER="pacman"
            PKG_UPDATE_CMD="pacman -Sy --noconfirm"
            PKG_INSTALL_CMD="pacman -S --noconfirm --needed"
            ;;
        arch|manjaro|endeavouros|garuda|cachyos|arcturus)
            PKG_MANAGER="pacman"
            PKG_UPDATE_CMD="pacman -Sy --noconfirm"
            PKG_INSTALL_CMD="pacman -S --noconfirm --needed"
            ;;
        ubuntu|debian|linuxmint|pop|kali|neon)
            PKG_MANAGER="apt"
            PKG_UPDATE_CMD="apt update -qq"
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
            ;;
        opensuse*|sles)
            PKG_MANAGER="zypper"
            PKG_UPDATE_CMD="zypper refresh"
            PKG_INSTALL_CMD="zypper install -y --no-confirm"
            ;;
        *)
            echo -e "${RED}ОШИБКА: Неподдерживаемая система: $ID ($PRETTY_NAME)${NC}"
            exit 1
            ;;
    esac
else
    echo -e "${RED}Не найден /etc/os-release${NC}"
    exit 1
fi

echo -e "${GREEN}Обнаружена система:${NC} $PRETTY_NAME"
echo -e "${GREEN}Менеджер пакетов:${NC} $PKG_MANAGER"
echo

# === 3. Архитектурные фиксы и ключи (PR Integration) ===
if [[ "$PKG_MANAGER" == "pacman" ]]; then
    echo -e "${BLUE}Настройка pacman (инициализация ключей)...${NC}"
    sudo pacman-key --init
    sudo pacman-key --populate archlinux
    if [[ "$IS_STEAMOS" == true ]]; then
        sudo pacman-key --populate holo
    fi
fi

# === 3a. Фиксы SteamOS с вопросами ===
if [[ "$IS_STEAMOS" == true ]]; then

    if ask_yes_no "Применить фикс openh264 (Discover)?" "y"; then
        echo -e "${BLUE}Установка openh264 фикса от Nospire...${NC}"
        bash <(curl -fsSL https://raw.githubusercontent.com/Nospire/fx/main/i) || \
            echo -e "${RED}Предупреждение: openh264 фикс не применён${NC}"
        sleep 2
    else
        echo -e "${WHITE}Фикс openh264 пропущен${NC}"
    fi

    if ask_yes_no "Обновить SteamOS?" "y"; then
        echo -e "${BLUE}Применяем сетевой фикс ngdt1...${NC}"
        curl -fsSL fix.geekcom.org/ngdt1 | bash || \
            echo -e "${RED}Предупреждение: ngdt1 фикс не применён${NC}"
        sleep 2
    else
        echo -e "${WHITE}Фикс SteamOS пропущен${NC}"
    fi

fi

# === 4. SteamOS: отключение readonly ===
readonly_was_enabled=false
if [[ "$IS_STEAMOS" == true ]] && command -v steamos-readonly >/dev/null 2>&1; then
    if mount | grep "on / " | grep -q "ro,"; then
        echo -e "${BLUE}SteamOS: временно отключаем readonly режим...${NC}"
        sudo steamos-readonly disable
        readonly_was_enabled=true
    fi
fi

# === 5. Проверка необходимых файлов ===
echo -e "${WHITE}Проверка наличия файлов...${NC}"
TEMP_DIR="$(pwd)"
required_files=(
    "main_script.sh"
    "stop_and_clean_nft.sh"
    "service.sh"
    "rename_bat.sh"
    "zapret_gui.py"
    "nfqws"
    "zapretdeck.png"
    "zapretdeck.desktop"
    "requirements.txt"
)

missing_files=()
for file in "${required_files[@]}"; do
    if [[ ! -e "$TEMP_DIR/$file" ]]; then
        missing_files+=("$file")
    fi
done

if [[ ${#missing_files[@]} -ne 0 ]]; then
    echo -e "${RED}ОШИБКА: Отсутствуют файлы в папке инсталлера:${NC}"
    for f in "${missing_files[@]}"; do echo -e "${RED}  ✗ $f${NC}"; done
    exit 1
fi

# === 6. Удаление старой установки ===
echo -e "${WHITE}Удаление предыдущих версий...${NC}"
sudo systemctl disable --now zapretdeck.service >/dev/null 2>&1 || true
sudo systemctl disable --now zapretdeck >/dev/null 2>&1 || true
sudo systemctl disable --now zapret_discord_youtube.service >/dev/null 2>&1 || true
sudo rm -rf /opt/zapretdeck
sudo rm -f /etc/systemd/system/zapretdeck.service
sudo rm -f /etc/systemd/system/zapretdeck
sudo rm -f /etc/systemd/system/zapret_discord_youtube.service
sudo rm -f /usr/local/bin/zapretdeck
sudo rm -f /usr/share/applications/zapretdeck.desktop
sudo systemctl daemon-reload

# === 7. Копирование файлов ===
echo -e "${BLUE}Копирование файлов в /opt/zapretdeck...${NC}"
sudo mkdir -p /opt/zapretdeck/{custom-strategies,zapret-latest}
sudo cp -r "$TEMP_DIR"/* /opt/zapretdeck/
sudo chmod +x /opt/zapretdeck/{main_script.sh,stop_and_clean_nft.sh,service.sh,rename_bat.sh,nfqws,zapret_gui.py}

# === 8. Установка системных зависимостей ===
echo -e "${BLUE}Установка системных зависимостей...${NC}"
install_dep() {
    local dep="$1"
    local pkg_name="${2:-$1}"
    if ! command -v "$dep" &>/dev/null; then
        echo -e "${WHITE}Установка $pkg_name...${NC}"
        case "$PKG_MANAGER" in
            pacman) sudo $PKG_INSTALL_CMD "$pkg_name" ;;
            apt) sudo $PKG_INSTALL_CMD "$pkg_name" ;;
            dnf|zypper) sudo $PKG_INSTALL_CMD "$pkg_name" ;;
            rpm-ostree) echo -e "${RED}На Bazzite/OSTree установите $pkg_name вручную${NC}" ;;
        esac
    fi
}

deps=("nft:nftables" "python3:python" "nmcli:NetworkManager" "ip:iproute2" "curl:curl")
for dep_pair in "${deps[@]}"; do
    install_dep "${dep_pair%%:*}" "${dep_pair##*:}"
done

# === 9. Python venv и зависимости ===
echo -e "${BLUE}Настройка виртуального окружения Python...${NC}"
sudo rm -rf /opt/zapretdeck/venv
sudo python3 -m venv /opt/zapretdeck/venv
sudo /opt/zapretdeck/venv/bin/pip install --upgrade pip setuptools wheel
sudo /opt/zapretdeck/venv/bin/pip install -r /opt/zapretdeck/requirements.txt PyQt6 packaging

# === 10. Конфигурация ===
sudo bash -c "cat > /opt/zapretdeck/conf.env" << 'EOF'
interface=any
auto_update=false
strategy=
gamefilter=false
EOF
sudo chmod 666 /opt/zapretdeck/conf.env

# === 11. Запускной файл и ярлык ===
sudo bash -c "cat > /usr/local/bin/zapretdeck" << 'EOF'
#!/bin/bash
exec /opt/zapretdeck/venv/bin/python3 /opt/zapretdeck/zapret_gui.py "$@"
EOF
sudo chmod +x /usr/local/bin/zapretdeck

# Установка ярлыка
if [[ "$PKG_MANAGER" == "rpm-ostree" ]]; then
    REAL_USER="${SUDO_USER:-$USER}"
    REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
    ICON_DEST="$REAL_HOME/.local/share/applications/zapretdeck.desktop"
    mkdir -p "$REAL_HOME/.local/share/applications"
    sudo cp /opt/zapretdeck/zapretdeck.desktop "$ICON_DEST"
    sudo chown "$REAL_USER:$REAL_USER" "$ICON_DEST"
else
    sudo cp /opt/zapretdeck/zapretdeck.desktop /usr/share/applications/
fi

sudo touch /opt/zapretdeck/debug.log
sudo chmod 666 /opt/zapretdeck/debug.log
sudo systemctl daemon-reload

# === 13. SteamOS: возврат readonly ===
if [[ "$readonly_was_enabled" == true ]]; then
    echo -e "${BLUE}SteamOS: возвращаем readonly режим...${NC}"
    sudo steamos-readonly enable
fi

# === ФИНИШ ===
echo
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║      ZapretDeck успешно установлен!      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo