#!/usr/bin/env bash
set -euo pipefail

# === BASE_DIR ===
BASE_DIR="/opt/zapretdeck"
SERVICE_NAME="zapretdeck"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
MAIN_SCRIPT="${BASE_DIR}/main_script.sh"
STOP_SCRIPT="${BASE_DIR}/stop_and_clean_nft.sh"
CONF_FILE="${BASE_DIR}/conf.env"
LOG_FILE="${BASE_DIR}/debug.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SERVICE] $*" | tee -a "$LOG_FILE"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log "ОШИБКА: скрипт должен запускаться от root (через sudo)"
        exit 1
    fi
}

check_conf_file() {
    if [[ ! -f "$CONF_FILE" ]]; then
        log "ОШИБКА: конфиг не найден: $CONF_FILE"
        log "Создаю базовый conf.env..."
        cat > "$CONF_FILE" <<EOF
interface=any
strategy=
gamefilter=false
auto_update=false
EOF
        chmod 666 "$CONF_FILE"
        log "Базовый conf.env создан"
    fi

    # Добавляем отсутствующие поля
    for field in interface strategy gamefilter auto_update; do
        if ! grep -q "^${field}=" "$CONF_FILE"; then
            log "ПРЕДУПРЕЖДЕНИЕ: добавляю отсутствующее поле $field в conf.env"
            echo "${field}=" >> "$CONF_FILE"
        fi
    done

    log "Текущий conf.env:"
    cat "$CONF_FILE" | sed 's/^/    /' | tee -a "$LOG_FILE"
}

install() {
    check_conf_file
    log "УСТАНОВКА фонового сервиса: $SERVICE_NAME (с автозапуском при загрузке)"

    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=ZapretDeck Background Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$BASE_DIR
EnvironmentFile=$CONF_FILE
ExecStartPre=/usr/bin/env bash "$STOP_SCRIPT"
ExecStart=/usr/bin/env bash "$MAIN_SCRIPT"
ExecStop=/usr/bin/env bash "$STOP_SCRIPT"
TimeoutStopSec=20
KillMode=mixed
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_FILE
StandardError=append:$LOG_FILE

[Install]
WantedBy=multi-user.target
EOF

    log "Юнит-файл создан: $SERVICE_FILE"

    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}.service" --now

    log "Сервис включён в автозагрузку и запущен (enable --now)"

    # Проверка активности
    for i in {1..15}; do
        sleep 1
        if systemctl is-active --quiet "${SERVICE_NAME}.service"; then
            log "УСПЕХ: сервис $SERVICE_NAME активен и работает"
            return 0
        fi
    done

    log "ОШИБКА: сервис не стал active после 15 секунд!"
    log "Вывод systemctl status:"
    systemctl status "${SERVICE_NAME}.service" --no-pager | tee -a "$LOG_FILE"
    return 1
}

remove() {
    log "УДАЛЕНИЕ фонового сервиса: $SERVICE_NAME"

    systemctl stop "${SERVICE_NAME}.service" 2>/dev/null || true
    systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true

    # Полная очистка
    rm -f "/etc/systemd/system/${SERVICE_NAME}"
    rm -f "$SERVICE_FILE"

    systemctl daemon-reload
    systemctl reset-failed "${SERVICE_NAME}.service" 2>/dev/null || true

    log "Сервис $SERVICE_NAME полностью удалён из системы и автозагрузки"
}

case "${1:-}" in
    install)
        check_root
        install
        ;;
    remove)
        check_root
        remove
        ;;
    *)
        echo "Использование: sudo $(basename "$0") {install|remove}"
        exit 1
        ;;
esac