#!/usr/bin/env bash

# Константы
SERVICE_NAME="zapret_discord_youtube"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
HOME_DIR_PATH="$(dirname "$0")"
MAIN_SCRIPT_PATH="$(dirname "$0")/main_script.sh"
CONF_FILE="$(dirname "$0")/conf.env"
STOP_SCRIPT="$(dirname "$0")/stop_and_clean_nft.sh"
LOG_FILE="/opt/zapretdeck/debug.log"

# Функция для логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Функция обработки ошибок
handle_error() {
    log "Ошибка: $1" >&2
    exit 1
}

# Функция для проверки существования conf.env и обязательных полей
check_conf_file() {
    if [[ ! -f "$CONF_FILE" ]]; then
        log "Файл конфигурации $CONF_FILE не найден, создаю с значениями по умолчанию"
        create_conf_file
    fi
    
    source "$CONF_FILE"
    interface=${interface:-any}
    auto_update=${auto_update:-false}
    strategy=${strategy:-$(find "$HOME_DIR_PATH/zapret-latest" -maxdepth 1 -type f -name "*.bat" | head -n 1 | xargs -n 1 basename 2>/dev/null)}
    
    if [[ -z "$strategy" ]]; then
        handle_error "Не найден ни один .bat файл в $HOME_DIR_PATH/zapret-latest"
    fi
    
    # Перезаписываем conf.env с заполненными значениями
    cat <<EOF > "$CONF_FILE"
interface=$interface
auto_update=$auto_update
strategy=$strategy
dns=disabled
EOF
    log "Конфигурация обновлена в $CONF_FILE"
    return 0
}

# Функция для создания файла конфигурации conf.env
create_conf_file() {
    local repo_dir="$HOME_DIR_PATH/zapret-latest"
    
    # 1. Интерфейс по умолчанию
    local interfaces=("any" $(ls /sys/class/net 2>/dev/null | grep -v lo))
    if [ ${#interfaces[@]} -eq 0 ]; then
        handle_error "Не найдены сетевые интерфейсы"
    fi
    local chosen_interface="any"
    
    # 2. Авто-обновление
    local auto_update_choice="false"
    
    # 3. Стратегия
    local strategy_choice=""
    if [[ -d "$repo_dir" ]]; then
        mapfile -t bat_files < <(find "$repo_dir" -maxdepth 1 -type f \( -name "*general*.bat" -o -name "*discord*.bat" \))
        if [ ${#bat_files[@]} -gt 0 ]; then
            strategy_choice="$(basename "${bat_files[0]}")"
        else
            handle_error "Файлы .bat с 'general' или 'discord' не найдены в $repo_dir"
        fi
    else
        handle_error "Папка репозитория $repo_dir не найдена"
    fi
    
    # Записываем значения в conf.env
    cat <<EOF > "$CONF_FILE"
interface=$chosen_interface
auto_update=$auto_update_choice
strategy=$strategy_choice
dns=disabled
EOF
    log "Конфигурация записана в $CONF_FILE"
}

# Функция для проверки статуса процесса nfqws
check_nfqws_status() {
    if pgrep -f "nfqws" >/dev/null; then
        log "Демоны nfqws запущены"
    else
        log "Демоны nfqws не запущены"
    fi
}

# Функция для проверки статуса сервиса
check_service_status() {
    if ! systemctl list-unit-files | grep -q "$SERVICE_NAME.service"; then
        log "Статус: Сервис не установлен"
        return 1
    fi
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log "Статус: Сервис установлен и активен"
        return 2
    else
        log "Статус: Сервис установлен, но не активен"
        return 3
    fi
}

# Функция для установки сервиса
install_service() {
    if ! check_conf_file; then
        handle_error "Не удалось создать корректный файл конфигурации"
    fi
    
    if ! sudo touch /etc/systemd/system/.test 2>/dev/null || ! sudo rm /etc/systemd/system/.test; then
        handle_error "Нет прав на запись в /etc/systemd/system"
    fi
    
    local absolute_homedir_path="/opt/zapretdeck"
    local absolute_main_script_path="/opt/zapretdeck/main_script.sh"
    local absolute_stop_script_path="/opt/zapretdeck/stop_and_clean_nft.sh"
    
    log "Создание systemd сервиса для автозагрузки..."
    sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=Zapret Discord/YouTube
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$absolute_homedir_path
User=root
ExecStart=/usr/bin/env bash $absolute_main_script_path -nointeractive
ExecStop=/usr/bin/env bash $absolute_stop_script_path
ExecStopPost=/usr/bin/env echo "Сервис завершён"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload 2>&1 | while read -r line; do log "systemctl: $line"; done
    sudo systemctl enable "$SERVICE_NAME" 2>&1 | while read -r line; do log "systemctl: $line"; done
    sudo systemctl start "$SERVICE_NAME" 2>&1 | while read -r line; do log "systemctl: $line"; done
    log "Сервис успешно установлен и запущен"
}

# Функция для удаления сервиса
remove_service() {
    log "Удаление сервиса..."
    sudo systemctl stop "$SERVICE_NAME" 2>&1 | while read -r line; do log "systemctl: $line"; done
    sudo systemctl disable "$SERVICE_NAME" 2>&1 | while read -r line; do log "systemctl: $line"; done
    sudo rm -f "$SERVICE_FILE"
    sudo systemctl daemon-reload 2>&1 | while read -r line; do log "systemctl: $line"; done
    log "Сервис удален"
}

# Функция для запуска сервиса
start_service() {
    log "Запуск сервиса..."
    sudo systemctl start "$SERVICE_NAME" 2>&1 | while read -r line; do log "systemctl: $line"; done
    log "Сервис запущен"
    sleep 3
    check_nfqws_status
}

# Функция для остановки сервиса
stop_service() {
    log "Остановка сервиса..."
    sudo systemctl stop "$SERVICE_NAME" 2>&1 | while read -r line; do log "systemctl: $line"; done
    log "Сервис остановлен"
    if [[ -x "$STOP_SCRIPT" ]]; then
        "$STOP_SCRIPT" 2>&1 | while read -r line; do log "stop_script: $line"; done
    else
        log "Скрипт остановки $STOP_SCRIPT не найден или не исполняемый"
    fi
}

# Функция для перезапуска сервиса
restart_service() {
    stop_service
    sleep 1
    start_service
}

# Основное меню управления
show_menu() {
    check_service_status
    local status=$?
    
    case $status in
        1)
            echo "1. Установить и запустить сервис"
            read -p "Выберите действие: " choice
            if [ "$choice" -eq 1 ]; then
                install_service
            fi
        ;;
        2)
            echo "1. Удалить сервис"
            echo "2. Остановить сервис"
            echo "3. Перезапустить сервис"
            read -p "Выберите действие: " choice
            case $choice in
                1) remove_service ;;
                2) stop_service ;;
                3) restart_service ;;
            esac
        ;;
        3)
            echo "1. Удалить сервис"
            echo "2. Запустить сервис"
            read -p "Выберите действие: " choice
            case $choice in
                1) remove_service ;;
                2) start_service ;;
            esac
        ;;
        *)
            echo "Неправильный выбор."
            ;;
    esac
}

# Запуск меню
show_menu