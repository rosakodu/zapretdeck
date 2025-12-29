#!/usr/bin/env bash

# === КОНСТАНТЫ ===
SERVICE_NAME="zapret_discord_youtube"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
HOME_DIR="/opt/zapretdeck"  # Жёстко задаём, как в GUI
MAIN_SCRIPT="$HOME_DIR/main_script.sh"
STOP_SCRIPT="$HOME_DIR/stop_and_clean_nft.sh"
CONF_FILE="$HOME_DIR/conf.env"
REPO_DIR="$HOME_DIR/zapret-latest"
LOG_FILE="$HOME_DIR/debug.log"

# === ЛОГИРОВАНИЕ ===
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [service.sh] $1" | tee -a "$LOG_FILE"
}

# === ОБРАБОТКА ОШИБОК ===
handle_error() {
    log "ОШИБКА: $1" >&2
    exit 1
}

# === ПРОВЕРКА КОНФИГА ===
check_conf_file() {
    if [[ ! -f "$CONF_FILE" ]]; then
        log "Файл конфигурации не найден — создаю с значениями по умолчанию"
        create_conf_file || handle_error "Не удалось создать conf.env"
    fi

    source "$CONF_FILE" 2>/dev/null

    interface=${interface:-any}
    auto_update=${auto_update:-false}
    strategy=${strategy:-""}

    # Поиск стратегии
    if [[ -z "$strategy" ]] || [[ ! -f "$REPO_DIR/$strategy" ]]; then
        log "Стратегия не указана или не существует — ищем .bat файл"
        mapfile -t bat_files < <(find "$REPO_DIR" -maxdepth 1 -type f \( -name "*general*.bat" -o -name "*discord*.bat" \) 2>/dev/null | head -n 1)
        if [[ ${#bat_files[@]} -gt 0 ]]; then
            strategy=$(basename "${bat_files[0]}")
            log "Выбрана стратегия: $strategy"
        else
            handle_error "Не найдено ни одного .bat файла с 'general' или 'discord' в $REPO_DIR"
        fi
    fi

    # Перезапись conf.env
    cat > "$CONF_FILE" <<EOF
interface=$interface
auto_update=$auto_update
strategy=$strategy
dns=${dns:-disabled}
dns_set_by_app=${dns_set_by_app:-disabled}
EOF
    log "Конфигурация обновлена: $strategy"
}

# === СОЗДАНИЕ КОНФИГА ===
create_conf_file() {
    [[ -d "$REPO_DIR" ]] || handle_error "Папка $REPO_DIR не существует"

    local default_strategy=""
    mapfile -t bat_files < <(find "$REPO_DIR" -maxdepth 1 -type f \( -name "*general*.bat" -o -name "*discord*.bat" \) 2>/dev/null | head -n 1)
    [[ ${#bat_files[@]} -gt 0 ]] && default_strategy=$(basename "${bat_files[0]}")

    [[ -n "$default_strategy" ]] || handle_error "Не найдено .bat файлов в $REPO_DIR"

    cat > "$CONF_FILE" <<EOF
interface=any
auto_update=false
strategy=$default_strategy
dns=disabled
dns_set_by_app=disabled
EOF
    log "Создан conf.env с стратегией: $default_strategy"
}

# === ПРОВЕРКА NFQWS ===
check_nfqws_status() {
    if pgrep -f "[n]fqws" > /dev/null; then
        log "nfqws процессы активны"
    else
        log "nfqws процессы не активны"
    fi
}

# === УСТАНОВКА СЕРВИСА ===
install_service() {
    check_conf_file

    log "Установка systemd-сервиса..."

    sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Zapret Discord/YouTube
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$HOME_DIR
User=root
EnvironmentFile=$CONF_FILE
ExecStart=/usr/bin/env bash $MAIN_SCRIPT -nointeractive
ExecStop=/usr/bin/env bash $STOP_SCRIPT
StandardOutput=journal
StandardError=journal
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload 2>&1 | while read -r line; do log "systemctl: $line"; done
    sudo systemctl enable "$SERVICE_NAME" --now 2>&1 | while read -r line; do log "systemctl: $line"; done
    log "Сервис установлен и запущен"
    check_nfqws_status
}

# === УДАЛЕНИЕ СЕРВИСА ===
remove_service() {
    log "Удаление сервиса..."
    sudo systemctl stop "$SERVICE_NAME" 2>/dev/null | while read -r line; do log "systemctl: $line"; done
    sudo systemctl disable "$SERVICE_NAME" 2>/dev/null | while read -r line; do log "systemctl: $line"; done
    sudo rm -f "$SERVICE_FILE"
    sudo systemctl daemon-reload 2>&1 | while read -r line; do log "systemctl: $line"; done
    log "Сервис удалён"
}

# === УПРАВЛЕНИЕ СЕРВИСОМ ===
start_service() {
    log "Запуск сервиса..."
    sudo systemctl start "$SERVICE_NAME" 2>&1 | while read -r line; do log "systemctl: $line"; done
    sleep 2
    check_nfqws_status
}

stop_service() {
    log "Остановка сервиса..."
    sudo systemctl stop "$SERVICE_NAME" 2>&1 | while read -r line; do log "systemctl: $line"; done
    if [[ -x "$STOP_SCRIPT" ]]; then
        sudo bash "$STOP_SCRIPT" 2>&1 | while read -r line; do log "stop_script: $line"; done
    fi
    check_nfqws_status
}

enable_service() {
    log "Включение автозапуска..."
    sudo systemctl enable "$SERVICE_NAME" 2>&1 | while read -r line; do log "systemctl: $line"; done
}

disable_service() {
    log "Отключение автозапуска..."
    sudo systemctl disable "$SERVICE_NAME" 2>&1 | while read -r line; do log "systemctl: $line"; done
}

# === ИНТЕРАКТИВНОЕ МЕНЮ (только если нет аргументов) ===
show_interactive_menu() {
    clear
    log "Запуск интерактивного меню"
    echo "=== ZapretDeck Service Manager ==="
    check_service_status
    local status=$?

    case $status in
        0) echo "Сервис не установлен" ;;
        1) echo "Сервис установлен, но не активен" ;;
        2) echo "Сервис активен" ;;
    esac

    echo
    echo "1) Установить и запустить сервис"
    echo "2) Остановить сервис"
    echo "3) Запустить сервис"
    echo "4) Перезапустить сервис"
    echo "5) Удалить сервис"
    echo "6) Проверить статус"
    echo "0) Выход"
    echo
    read -p "Выберите действие: " choice

    case $choice in
        1) install_service; read -p "Нажмите Enter..." ;;
        2) stop_service; read -p "Нажмите Enter..." ;;
        3) start_service; read -p "Нажмите Enter..." ;;
        4) stop_service; sleep 1; start_service; read -p "Нажмите Enter..." ;;
        5) remove_service; read -p "Нажмите Enter..." ;;
        6) check_nfqws_status; systemctl status "$SERVICE_NAME" 2>/dev/null || echo "Сервис не установлен"; read -p "Нажмите Enter..." ;;
        0) log "Выход из меню"; exit 0 ;;
        *) echo "Неверный выбор"; sleep 1 ;;
    esac
    show_interactive_menu
}

# === ПРОВЕРКА СТАТУСА СЕРВИСА ===
check_service_status() {
    if [[ ! -f "$SERVICE_FILE" ]]; then
        return 0  # не установлен
    elif systemctl is-active --quiet "$SERVICE_NAME"; then
        return 2  # активен
    else
        return 1  # установлен, но не активен
    fi
}

# === ОСНОВНАЯ ЛОГИКА ===
# Если есть аргументы — выполняем команду
if [[ $# -gt 0 ]]; then
    case "$1" in
        install) install_service ;;
        remove) remove_service ;;
        start) start_service ;;
        stop) stop_service ;;
        enable) enable_service ;;
        disable) disable_service ;;
        restart) stop_service; sleep 1; start_service ;;
        status) check_service_status; exit $? ;;
        *) log "Неизвестная команда: $1"; exit 1 ;;
    esac
else
    # Нет аргументов — запускаем меню
    show_interactive_menu
fi