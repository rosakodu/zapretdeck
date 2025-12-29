#!/bin/bash
# dns.sh — ПРОСТОЙ И ЧИСТЫЙ DNS
# set: УСТАНАВЛИВАЕТ DNS через NetworkManager
# unset: СТИРАЕТ DNS → DHCP
# Только активные интерфейсы (кроме lo)

LOG_FILE="/opt/zapretdeck/debug.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DNS] $*" >> "$LOG_FILE"; }

# === УСТАНОВКА DNS ===
set_dns() {
    log "ВКЛЮЧЕНИЕ DNS: 176.99.11.77 80.78.247.254"

    for con in $(nmcli -t -f NAME con show --active | cut -d: -f1 | grep -v '^lo$'); do
        log "Установка на: $con"
        if nmcli con mod "$con" \
             ipv4.dns "176.99.11.77 80.78.247.254" \
             ipv4.dns-priority -100 \
             ipv4.ignore-auto-dns yes && \
           nmcli con up "$con" >/dev/null 2>&1; then
            log "УСПЕХ: $con"
        else
            log "ОШИБКА: $con"
            return 1
        fi
    done

    systemctl try-restart systemd-resolved >/dev/null 2>&1 || true
    log "DNS УСТАНОВЛЕН"
    return 0
}

# === СТИРАНИЕ DNS ===
unset_dns() {
    log "ОТКЛЮЧЕНИЕ DNS → возврат к DHCP"

    for con in $(nmcli -t -f NAME con show --active | cut -d: -f1 | grep -v '^lo$'); do
        log "Стирание с: $con"
        if nmcli con mod "$con" \
             ipv4.dns "" \
             ipv4.dns-priority 0 \
             ipv4.ignore-auto-dns no && \
           nmcli con up "$con" >/dev/null 2>&1; then
            log "УСПЕХ: $con"
        else
            log "ОШИБКА: $con"
            return 1
        fi
    done

    systemctl try-restart systemd-resolved >/dev/null 2>&1 || true
    log "DNS ОТКЛЮЧЁН"
    return 0
}

# === ОСНОВНАЯ ЛОГИКА ===
case "$1" in
    set)   set_dns ;;
    unset) unset_dns ;;
    *)     log "Использование: $0 {set|unset}"; exit 1 ;;
esac

exit $?