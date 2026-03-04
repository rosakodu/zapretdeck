#!/bin/bash
set -e
# === ЦВЕТА ===
WHITE='\033[1;37m'
BLUE='\033[1;34m'
RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# === ФУНКЦИЯ ЛОГИРОВАНИЯ ===
log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local color="$NC"
    
    case "$level" in
        INFO)    color="$GREEN" ;;
        WARNING) color="$YELLOW" ;;
        ERROR)   color="$RED" ;;
        DEBUG)   color="$WHITE" ;;
    esac
    
    echo -e "${color}[$timestamp] [$level] $message${NC}" | tee -a "$LOG_FILE"
}
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
# Лог-файл для отладки
LOG_FILE="$HOME/zapretdeck_install.log"
echo -e "=== Начало установки $(date) ===" | tee "$LOG_FILE"

# === Защита от запуска "как root" напрямую ===
# Скрипт должен запускаться от обычного пользователя, а sudo используется только внутри.
if [[ "$EUID" -eq 0 && -z "$SUDO_USER" ]]; then
    echo -e "${RED}Не запускайте install.sh напрямую от root (например, 'sudo su' + './install.sh').${NC}" | tee -a "$LOG_FILE"
    echo -e "${RED}Пожалуйста, запустите установку так:${NC}" | tee -a "$LOG_FILE"
    echo -e "${WHITE}  bash install.sh${NC}" | tee -a "$LOG_FILE"
    echo -e "${WHITE}Скрипт сам запросит sudo-пароль при необходимости.${NC}" | tee -a "$LOG_FILE"
    exit 1
fi
# === 0. Функция Да / Нет для фиксов ===
ask_yes_no() {
    local question="$1"
    local default="$2" # y / n
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
            n|no) return 1 ;;
            *) echo -e "${YELLOW}Введите y или n${NC}" ;;
        esac
    done
}
# === 1. Проверка sudo ===
echo -e "${WHITE}Проверка прав sudo...${NC}" | tee -a "$LOG_FILE"
if ! sudo -n true 2>/dev/null; then
    echo -e "${WHITE}Введите пароль sudo для установки:${NC}" | tee -a "$LOG_FILE"
    sudo true || { echo -e "${RED}Ошибка: Неверный пароль sudo.${NC}" | tee -a "$LOG_FILE"; exit 1; }
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
        arch|manjaro|endeavouros|garuda|cachyos|arcturus|rebornos|vanillaos)
            PKG_MANAGER="pacman"
            PKG_UPDATE_CMD="pacman -Sy --noconfirm"
            PKG_INSTALL_CMD="pacman -S --noconfirm --needed"
            ;;
        steamos|chimeraos|steamfork|holoiso)
            IS_STEAMOS=true
            PKG_MANAGER="pacman"
            PKG_UPDATE_CMD="pacman -Sy --noconfirm"
            PKG_INSTALL_CMD="pacman -S --noconfirm --needed"
            ;;
        ubuntu|debian|linuxmint|pop|kali|neon|linuxlite|elementary|zorin)
            PKG_MANAGER="apt"
            PKG_UPDATE_CMD="apt update -qq"
            PKG_INSTALL_CMD="apt install -y"
            ;;
        alt|altlinux|basealt|ximper|aspenite)
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
            echo -e "${RED}ОШИБКА: Неподдерживаемая система: $ID ($PRETTY_NAME)${NC}" | tee -a "$LOG_FILE"
            exit 1
            ;;
    esac
else
    echo -e "${RED}Не найден /etc/os-release${NC}" | tee -a "$LOG_FILE"
    exit 1
fi
echo -e "${GREEN}Обнаружена система:${NC} $PRETTY_NAME" | tee -a "$LOG_FILE"
echo -e "${GREEN}Менеджер пакетов:${NC} $PKG_MANAGER" | tee -a "$LOG_FILE"
echo | tee -a "$LOG_FILE"
# === 3. Архитектурные фиксы и ключи ===
if [[ "$PKG_MANAGER" == "pacman" ]]; then
    echo -e "${BLUE}Настройка pacman (инициализация ключей)...${NC}" | tee -a "$LOG_FILE"
    sudo pacman-key --init 2>&1 | tee -a "$LOG_FILE"
    sudo pacman-key --populate archlinux 2>&1 | tee -a "$LOG_FILE"
    if [[ "$IS_STEAMOS" == true ]]; then
        sudo pacman-key --populate holo 2>&1 | tee -a "$LOG_FILE"
    fi
fi
# === 3a. SteamOS фиксы с вопросами ===
# Фиксы openh264 и обновления SteamOS удалены
# === 3b. Обновление репозиториев ===
echo -e "${BLUE}Обновление репозиториев...${NC}" | tee -a "$LOG_FILE"
if [[ "$PKG_MANAGER" != "rpm-ostree" ]]; then
    sudo $PKG_UPDATE_CMD 2>&1 | tee -a "$LOG_FILE" || echo -e "${YELLOW}Предупреждение: Обновление репозиториев не удалось${NC}" | tee -a "$LOG_FILE"
else
    echo -e "${YELLOW}Для Bazzite обновите систему вручную после установки: rpm-ostree upgrade${NC}" | tee -a "$LOG_FILE"
fi
# === 4. SteamOS: отключение readonly ===
readonly_was_enabled=false
if [[ "$IS_STEAMOS" == true ]] && command -v steamos-readonly >/dev/null 2>&1; then
    if mount | grep "on / " | grep -q "ro,"; then
        echo -e "${BLUE}SteamOS: временно отключаем readonly режим...${NC}" | tee -a "$LOG_FILE"
        sudo steamos-readonly disable 2>&1 | tee -a "$LOG_FILE"
        readonly_was_enabled=true
    fi
fi
# === 5. Проверка необходимых файлов ===
echo -e "${WHITE}Проверка наличия файлов...${NC}" | tee -a "$LOG_FILE"
TEMP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
required_files=(
    "main_script.sh"
    "stop_and_clean_nft.sh"
    "service.sh"
    "rename_bat.sh"
    "main.py"
    "config.py"
    "ui.py"
    "utils.py"
    "monitor.py"
    "nfqws"
    "sys_utils.py"
    "requirements.txt"
    "main_script.sh"
    "stop_and_clean_nft.sh"
    "service.sh"
    "rename_bat.sh"
    "main.py"
    "config.py"
    "ui.py"
    "utils.py"
    "monitor.py"
    "nfqws"
    "zapretdeck.png"
    "zapretdeck.desktop"
    "zapretdeck"
    "ad"
)
missing_files=()
for file in "${required_files[@]}"; do
    if [[ ! -e "$TEMP_DIR/$file" ]]; then
        missing_files+=("$file")
    fi
done
if [[ ${#missing_files[@]} -ne 0 ]]; then
    echo -e "${RED}ОШИБКА: Отсутствуют файлы в папке инсталлера:${NC}" | tee -a "$LOG_FILE"
    for f in "${missing_files[@]}"; do echo -e "${RED} ✗ $f${NC}" | tee -a "$LOG_FILE"; done
    exit 1
fi
# === 6. Удаление старой установки ===
echo -e "${WHITE}Удаление предыдущих версий...${NC}" | tee -a "$LOG_FILE"
sudo systemctl disable --now zapretdeck.service >/dev/null 2>&1 || true
sudo systemctl disable --now zapretdeck >/dev/null 2>&1 || true
sudo systemctl disable --now zapret_discord_youtube.service >/dev/null 2>&1 || true
sudo rm -rf /opt/zapretdeck 2>&1 | tee -a "$LOG_FILE"
sudo rm -f /etc/systemd/system/zapretdeck.service 2>&1 | tee -a "$LOG_FILE"
sudo rm -f /etc/systemd/system/zapretdeck 2>&1 | tee -a "$LOG_FILE"
sudo rm -f /etc/systemd/system/zapret_discord_youtube.service 2>&1 | tee -a "$LOG_FILE"
sudo rm -f /usr/local/bin/zapretdeck 2>&1 | tee -a "$LOG_FILE"
sudo rm -f /usr/share/applications/zapretdeck.desktop 2>&1 | tee -a "$LOG_FILE"
sudo systemctl daemon-reload 2>&1 | tee -a "$LOG_FILE"

# Определение домашнего каталога пользователя
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
INSTALL_DIR="$REAL_HOME/zapretdeck"

# Удаление старой установки из домашнего каталога пользователя
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${WHITE}Удаление старой установки из $INSTALL_DIR...${NC}" | tee -a "$LOG_FILE"
    # Пытаемся удалить от имени пользователя; если нет прав — удаляем через sudo
    if ! rm -rf "$INSTALL_DIR" 2>>"$LOG_FILE"; then
        echo -e "${YELLOW}Нет прав на удаление $INSTALL_DIR, пробуем через sudo...${NC}" | tee -a "$LOG_FILE"
        sudo rm -rf "$INSTALL_DIR" 2>&1 | tee -a "$LOG_FILE" || {
            echo -e "${RED}Не удалось удалить старую установку в $INSTALL_DIR${NC}" | tee -a "$LOG_FILE"
        }
    fi
fi

# Удаление всех старых ярлыков и скриптов пользователя
rm -f "$REAL_HOME/.local/bin/zapretdeck" 2>/dev/null || true
rm -f "$REAL_HOME/.local/share/applications/zapretdeck.desktop" 2>/dev/null || true
sudo rm -f /usr/local/share/applications/zapretdeck.desktop 2>/dev/null || true
sudo rm -f /usr/share/applications/zapretdeck.desktop 2>/dev/null || true

# Удаление старых скриптов запуска из системных директорий
sudo rm -f /usr/local/bin/zapretdeck 2>/dev/null || true
sudo rm -f /usr/bin/zapretdeck 2>/dev/null || true

# Удаление старых директорий (ZapretDeck с большой буквы и другие вариации)
rm -rf "$REAL_HOME/ZapretDeck" 2>/dev/null || true
rm -rf "$REAL_HOME/zapret" 2>/dev/null || true

echo -e "${GREEN}Старые версии удалены${NC}" | tee -a "$LOG_FILE"
# === 7. Копирование файлов ===
echo -e "${BLUE}Копирование файлов в $INSTALL_DIR...${NC}" | tee -a "$LOG_FILE"
mkdir -p "$INSTALL_DIR"/{custom-strategies,zapret-latest,i18n,ad} 2>&1 | tee -a "$LOG_FILE"

# Гарантируем, что каталог установки принадлежит реальному пользователю,
# чтобы избежать ошибок Permission denied при копировании и компиляции переводов
sudo chown -R "$REAL_USER":"$REAL_USER" "$INSTALL_DIR" 2>/dev/null || true

cp -r "$TEMP_DIR"/* "$INSTALL_DIR"/ 2>&1 | tee -a "$LOG_FILE"

# Проверка и копирование каталога ad с файлами
if [ -d "$TEMP_DIR/ad" ]; then
    echo -e "${WHITE}Копирование каталога ad...${NC}" | tee -a "$LOG_FILE"
    if [ -f "$TEMP_DIR/ad/buyvpn.png" ]; then
        cp "$TEMP_DIR/ad/buyvpn.png" "$INSTALL_DIR/ad/" 2>&1 | tee -a "$LOG_FILE"
        echo -e "${GREEN}✓ Файл buyvpn.png скопирован${NC}" | tee -a "$LOG_FILE"
    else
        echo -e "${YELLOW}⚠ Файл buyvpn.png не найден в каталоге ad${NC}" | tee -a "$LOG_FILE"
    fi
else
    echo -e "${YELLOW}⚠ Каталог ad не найден${NC}" | tee -a "$LOG_FILE"
fi
chmod +x "$INSTALL_DIR"/{main_script.sh,stop_and_clean_nft.sh,service.sh,rename_bat.sh,nfqws,main.py,config.py,zapretdeck} 2>&1 | tee -a "$LOG_FILE"
# === 8. Установка системных зависимостей ===
echo -e "${BLUE}Установка системных зависимостей...${NC}" | tee -a "$LOG_FILE"
install_dep() {
    local dep="$1"
    local pkg_name="${2:-$1}"
    if ! command -v "$dep" &>/dev/null; then
        echo -e "${WHITE}Установка $pkg_name...${NC}" | tee -a "$LOG_FILE"
        if [[ "$PKG_MANAGER" == "rpm-ostree" ]]; then
            echo -e "${YELLOW}Для Bazzite установите $pkg_name вручную: rpm-ostree install $pkg_name && rpm-ostree apply-live${NC}" | tee -a "$LOG_FILE"
            return 1
        else
            sudo $PKG_INSTALL_CMD "$pkg_name" 2>&1 | tee -a "$LOG_FILE" || { echo -e "${RED}Ошибка: Не удалось установить $pkg_name${NC}" | tee -a "$LOG_FILE"; return 1; }
        fi
    else
        echo -e "${GREEN}$pkg_name уже установлен${NC}" | tee -a "$LOG_FILE"
    fi
    return 0
}
deps=("nft:nftables" "python3:python" "nmcli:NetworkManager" "ip:iproute2" "curl:curl" "git:git" "gcc-libs:gcc-libs")

# System-specific python venv package
case "$PKG_MANAGER" in
    apt) deps+=("python3-venv:python3-venv") ;;
    dnf) ;; # usually included
    pacman) ;; # usually included
    zypper) ;; # usually included
esac

all_deps_ok=true
for dep_pair in "${deps[@]}"; do
    install_dep "${dep_pair%%:*}" "${dep_pair##*:}" || all_deps_ok=false
done

# Install Qt tools for translation compilation if needed
echo -e "${WHITE}Установка инструментов для компиляции переводов...${NC}" | tee -a "$LOG_FILE"
case "$PKG_MANAGER" in
    pacman) install_dep "lrelease" "qt6-base" || echo -e "${YELLOW}Qt tools не установлены (опционально)${NC}" | tee -a "$LOG_FILE" ;;
    apt) install_dep "lrelease" "qttools5-dev-tools" || echo -e "${YELLOW}Qt tools не установлены (опционально)${NC}" | tee -a "$LOG_FILE" ;;
    dnf) install_dep "lrelease" "qt6-linguist" || echo -e "${YELLOW}Qt tools не установлены (опционально)${NC}" | tee -a "$LOG_FILE" ;;
    zypper) install_dep "lrelease" "qt6-tools" || echo -e "${YELLOW}Qt tools не установлены (опционально)${NC}" | tee -a "$LOG_FILE" ;;
esac
if [[ "$all_deps_ok" == false ]]; then
    echo -e "${YELLOW}Предупреждение: Некоторые системные зависимости не установлены. Установите их вручную.${NC}" | tee -a "$LOG_FILE"
fi
# === 9. Создание Virtual Environment ===
echo -e "${BLUE}Настройка Python Virtual Environment...${NC}" | tee -a "$LOG_FILE"

VENV_DIR="$INSTALL_DIR/venv"

# Remove old venv if it exists and looks broken, or just to be safe?
# For now, we try to create it.
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${WHITE}Создание venv в $VENV_DIR...${NC}" | tee -a "$LOG_FILE"
    python3 -m venv "$VENV_DIR" 2>&1 | tee -a "$LOG_FILE" || {
        echo -e "${RED}Ошибка: Не удалось создать venv. Убедитесь, что python3-venv установлен.${NC}" | tee -a "$LOG_FILE"
        exit 1
    }
else
    echo -e "${GREEN}venv уже существует${NC}" | tee -a "$LOG_FILE"
fi

# Activate venv for installation
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo -e "${WHITE}Обновление pip...${NC}" | tee -a "$LOG_FILE"
pip install --upgrade pip 2>&1 | tee -a "$LOG_FILE"

# Install requirements
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    echo -e "${WHITE}Установка зависимостей из requirements.txt...${NC}" | tee -a "$LOG_FILE"
    pip install -r "$INSTALL_DIR/requirements.txt" 2>&1 | tee -a "$LOG_FILE" || {
        echo -e "${RED}Ошибка установки зависимостей pip${NC}" | tee -a "$LOG_FILE"
        exit 1
    }
else
    echo -e "${YELLOW}Предупреждение: requirements.txt не найден!${NC}" | tee -a "$LOG_FILE"
fi

echo -e "${GREEN}Python окружение настроено${NC}" | tee -a "$LOG_FILE"

# Deactivate to avoid side effects
deactivate
# === 10. Конфигурация ===
echo -e "${BLUE}Создание конфигурации...${NC}" | tee -a "$LOG_FILE"
bash -c "cat > $INSTALL_DIR/conf.env" << 'EOF'
interface=any
auto_update=false
strategy=
gamefilter=false
EOF
chmod 666 "$INSTALL_DIR/conf.env" 2>&1 | tee -a "$LOG_FILE"
# === 10a. Компиляция переводов ===
echo -e "${BLUE}Компиляция переводов...${NC}" | tee -a "$LOG_FILE"
if command -v lrelease-qt6 >/dev/null 2>&1; then
    LRELEASE_CMD="lrelease-qt6"
elif command -v lrelease >/dev/null 2>&1; then
    LRELEASE_CMD="lrelease"
else
    LRELEASE_CMD=""
fi

if [ -n "$LRELEASE_CMD" ]; then
    for ts_file in "$INSTALL_DIR/i18n/"*.ts; do
        if [ -f "$ts_file" ]; then
            echo -e "${WHITE}Компилируем перевод: $(basename "$ts_file")${NC}" | tee -a "$LOG_FILE"
            $LRELEASE_CMD "$ts_file" -qm "${ts_file%.ts}.qm" 2>&1 | grep -v "^\[notice\]" | tee -a "$LOG_FILE" || {
                echo -e "${YELLOW}Предупреждение: Не удалось скомпилировать перевод: $(basename "$ts_file")${NC}" | tee -a "$LOG_FILE"
                # Создаём пустой .qm файл как запасной вариант
                touch "${ts_file%.ts}.qm" 2>/dev/null || true
            }
        fi
    done
else
    echo -e "${YELLOW}lrelease не найден, создаём пустые .qm файлы как запасной вариант${NC}" | tee -a "$LOG_FILE"
    for ts_file in "$INSTALL_DIR/i18n/"*.ts; do
        if [ -f "$ts_file" ]; then
            qm_file="${ts_file%.ts}.qm"
            echo -e "${WHITE}Создаём пустой файл: $(basename "$qm_file")${NC}" | tee -a "$LOG_FILE"
            touch "$qm_file" 2>/dev/null || true
        fi
    done
fi
# === 10b. Установка WARP (исправленная версия) ===
if [[ "$PKG_MANAGER" == "pacman" ]]; then
    # Информируем пользователя об условиях использования WARP
    echo
    echo -e "${YELLOW}При установке и использовании Cloudflare WARP вы подтверждаете своё согласие с условиями Cloudflare...${NC}" | tee -a "$LOG_FILE"

    if ask_yes_no "Установить Cloudflare WARP?" "y"; then
        echo -e "${BLUE}Установка WARP...${NC}" | tee -a "$LOG_FILE"

        # Проверяем, уже настроен ли Chaotic-AUR (чтобы не ломать свежий mirrorlist)
        if ! grep -q "^\[chaotic-aur\]" /etc/pacman.conf 2>/dev/null; then
            echo -e "${WHITE}Настройка репозитория Chaotic-AUR (первый раз)...${NC}" | tee -a "$LOG_FILE"

            sudo pacman-key --init 2>&1 | tee -a "$LOG_FILE"
            sudo pacman-key --populate 2>&1 | tee -a "$LOG_FILE"

            sudo pacman-key --recv-key 3056513887B78AEB --keyserver keyserver.ubuntu.com 2>&1 | tee -a "$LOG_FILE"
            sudo pacman-key --lsign-key 3056513887B78AEB 2>&1 | tee -a "$LOG_FILE"

            # Ключ и mirrorlist с защитой от отката
            sudo pacman -U --noconfirm --needed \
                'https://cdn-mirror.chaotic.cx/chaotic-aur/chaotic-keyring.pkg.tar.zst' 2>&1 | tee -a "$LOG_FILE"

            sudo pacman -U --noconfirm --needed \
                'https://cdn-mirror.chaotic.cx/chaotic-aur/chaotic-mirrorlist.pkg.tar.zst' 2>&1 | tee -a "$LOG_FILE"

            if ! grep -q "^\[chaotic-aur\]" /etc/pacman.conf; then
                echo -e "\n[chaotic-aur]\nInclude = /etc/pacman.d/chaotic-mirrorlist" | sudo tee -a /etc/pacman.conf
            fi

            sudo pacman -Sy 2>&1 | tee -a "$LOG_FILE"
        else
            echo -e "${GREEN}Chaotic-AUR уже настроен, пропускаем bootstrap${NC}" | tee -a "$LOG_FILE"
            sudo pacman -Sy 2>&1 | tee -a "$LOG_FILE"
        fi

        # Гарантируем gcc-libs
        sudo pacman -S --noconfirm --needed gcc-libs 2>&1 | tee -a "$LOG_FILE"

        # Устанавливаем пакет, игнорируя баговую зависимость libgcc
        echo -e "${WHITE}Установка cloudflare-warp-bin...${NC}" | tee -a "$LOG_FILE"
        if sudo pacman -S --noconfirm --needed --assume-installed libgcc cloudflare-warp-bin 2>&1 | tee -a "$LOG_FILE"; then
            echo -e "${GREEN}WARP успешно установлен${NC}" | tee -a "$LOG_FILE"

            # Настройка сервисов
            echo -e "${WHITE}Настройка сервисов WARP...${NC}" | tee -a "$LOG_FILE"
            sudo systemctl enable --now warp-svc.service 2>&1 | tee -a "$LOG_FILE"

            # Пользовательский taskbar (если сессия активна)
            if [ -n "$DBUS_SESSION_BUS_ADDRESS" ] || DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus systemctl --user status >/dev/null 2>&1; then
                systemctl --user enable --now warp-taskbar 2>&1 | tee -a "$LOG_FILE" || true
            fi
        else
            echo -e "${RED}Не удалось установить cloudflare-warp-bin даже с обходом зависимости.${NC}" | tee -a "$LOG_FILE"
            echo -e "${YELLOW}Попробуй установить вручную после скрипта:${NC}" | tee -a "$LOG_FILE"
            echo -e "   sudo pacman -S --needed --assume-installed libgcc cloudflare-warp-bin" | tee -a "$LOG_FILE"
        fi
    else
        echo -e "${WHITE}Установка WARP пропущена${NC}" | tee -a "$LOG_FILE"
    fi
fi
# === 11. Финальная настройка ===
mkdir -p "$REAL_HOME/.local/bin" 2>&1 | tee -a "$LOG_FILE"

# Удаляем старые скрипты запуска (включая с путями к venv)
rm -f "$REAL_HOME/.local/bin/zapretdeck" 2>/dev/null || true
rm -f /usr/local/bin/zapretdeck 2>/dev/null || true

# Создаём новый скрипт запуска
bash -c "cat > $REAL_HOME/.local/bin/zapretdeck" << 'EOF'
#!/bin/bash
# ZapretDeck launcher script
cd "$HOME/zapretdeck"
# Activate venv and run
if [ -f "venv/bin/python3" ]; then
    exec ./venv/bin/python3 main.py "$@"
else
    echo "Error: venv not found. Please run install.sh again."
    exit 1
fi
EOF
chmod +x "$REAL_HOME/.local/bin/zapretdeck" 2>&1 | tee -a "$LOG_FILE"

# PATH
if ! grep -q '.local/bin' "$REAL_HOME/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$REAL_HOME/.bashrc" 2>&1
fi
if [ -f "$REAL_HOME/.zshrc" ] && ! grep -q '.local/bin' "$REAL_HOME/.zshrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$REAL_HOME/.zshrc" 2>&1
fi
export PATH="$REAL_HOME/.local/bin:$PATH"
# === Создание .desktop ярлыка ===
echo -e "${WHITE}Создание ярлыка...${NC}" | tee -a "$LOG_FILE"
mkdir -p "$REAL_HOME/.local/share/applications" 2>&1 | tee -a "$LOG_FILE"

# Определяем путь к иконке (с запасным вариантом)
ICON="$INSTALL_DIR/zapretdeck.png"
if [ ! -f "$ICON" ]; then
    ICON="/usr/share/icons/hicolor/256x256/apps/zapretdeck.png"
fi

# Создаём .desktop файл заново с корректными путями
cat > "$REAL_HOME/.local/share/applications/zapretdeck.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=ZapretDeck
GenericName=Обход блокировок
Comment=Инструмент обхода блокировок (YouTube, Discord и др.)
Exec=$REAL_HOME/.local/bin/zapretdeck
Icon=$ICON
Terminal=false
Categories=Network;Internet;Utility;
StartupWMClass=zapretdeck
EOF

chmod 644 "$REAL_HOME/.local/share/applications/zapretdeck.desktop" 2>&1 | tee -a "$LOG_FILE"
update-desktop-database "$REAL_HOME/.local/share/applications" 2>/dev/null || true

# Проверка и финальное сообщение
if [ -f "$REAL_HOME/.local/share/applications/zapretdeck.desktop" ]; then
    echo -e "${GREEN}Ярлык успешно создан${NC}" | tee -a "$LOG_FILE"
else
    echo -e "${RED}Ошибка: не удалось создать ярлык${NC}" | tee -a "$LOG_FILE"
fi
sudo systemctl daemon-reload 2>&1 | tee -a "$LOG_FILE"
# === 12. SteamOS: возврат readonly ===
if [[ "$readonly_was_enabled" == true ]]; then
    echo -e "${BLUE}Возврат readonly режима...${NC}" | tee -a "$LOG_FILE"
    sudo steamos-readonly enable 2>&1 | tee -a "$LOG_FILE"
fi
# === ФИНИШ ===
echo
echo -e "${WHITE}Запустите приложение через терминал командой: zapretdeck${NC}"
echo
echo -e "${WHITE}Ярлык создан и находится в меню приложений${NC}"
echo

# === ПРОВЕРКА УСТАНОВКИ ===
echo -e "${BLUE}Выполняем проверку установки...${NC}" | tee -a "$LOG_FILE"
if command -v zapretdeck >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Команда zapretdeck доступна${NC}" | tee -a "$LOG_FILE"
else
    echo -e "${RED}✗ Команда zapretdeck недоступна${NC}" | tee -a "$LOG_FILE"
fi

# Проверяем наличие основных компонентов
if [ -f "$INSTALL_DIR/main.py" ]; then
    echo -e "${GREEN}✓ Основные файлы приложения установлены${NC}" | tee -a "$LOG_FILE"
else
    echo -e "${RED}✗ Основные файлы приложения отсутствуют${NC}" | tee -a "$LOG_FILE"
fi

# Проверяем зависимости
missing_deps=()
for dep in ip nft nmcli pgrep pkill bash curl; do
    if ! command -v "$dep" &>/dev/null; then
        missing_deps+=("$dep")
    fi
done

if [ ${#missing_deps[@]} -eq 0 ]; then
    echo -e "${GREEN}✓ Все системные зависимости установлены${NC}" | tee -a "$LOG_FILE"
else
    echo -e "${RED}✗ Отсутствуют системные зависимости:${NC}" | tee -a "$LOG_FILE"
    for dep in "${missing_deps[@]}"; do
        echo -e "${RED}  - $dep${NC}" | tee -a "$LOG_FILE"
    done
    echo -e "${YELLOW}Установите отсутствующие зависимости вручную${NC}" | tee -a "$LOG_FILE"
fi

# Проверяем Python зависимости в venv
if [ -f "$INSTALL_DIR/venv/bin/python3" ]; then
    "$INSTALL_DIR/venv/bin/python3" -c "import PyQt6, packaging, requests" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Python зависимости установлены в venv${NC}" | tee -a "$LOG_FILE"
    else
        echo -e "${RED}✗ Python зависимости не установлены полностью в venv${NC}" | tee -a "$LOG_FILE"
    fi
else
    echo -e "${RED}✗ Virtual Environment не найден${NC}" | tee -a "$LOG_FILE"
fi

# Проверяем скрипт запуска
if [ -f "$REAL_HOME/.local/bin/zapretdeck" ]; then
    echo -e "${GREEN}✓ Скрипт запуска создан: $REAL_HOME/.local/bin/zapretdeck${NC}" | tee -a "$LOG_FILE"
    # Проверяем содержимое скрипта
    if grep -q "venv/bin/python3" "$REAL_HOME/.local/bin/zapretdeck"; then
        echo -e "${GREEN}✓ Скрипт запуска настроен правильно${NC}" | tee -a "$LOG_FILE"
    else
        echo -e "${RED}✗ Скрипт запуска содержит некорректный путь${NC}" | tee -a "$LOG_FILE"
    fi
else
    echo -e "${RED}✗ Скрипт запуска не создан${NC}" | tee -a "$LOG_FILE"
fi
echo
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                ZapretDeck                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo