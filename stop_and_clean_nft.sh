#!/bin/bash

cd /opt/zapretdeck || { echo "Ошибка: директория /opt/zapretdeck не существует"; exit 1; }

LOG_FILE="/opt/zapretdeck/debug.log"
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Остановка всех процессов nfqws
log "Остановка всех процессов nfqws..."
pkill -f "nfqws" && log "Процессы nfqws успешно остановлены" || log "Процессы nfqws не найдены"

# Очистка правил nftables
log "Очистка правил nftables, добавленных скриптом..."
if nft list table inet zapretunix >/dev/null 2>&1; then
    nft delete rule inet zapretunix output comment "Added by zapret script" >/dev/null 2>&1 && log "Правила с меткой 'Added by zapret script' удалены"
    nft flush table inet zapretunix >/dev/null 2>&1
    nft delete table inet zapretunix >/dev/null 2>&1 && log "Таблица inet zapretunix и цепочка output удалены"
else
    log "Таблица inet zapretunix не найдена. Нечего очищать."
fi

# Отключение DNS
log "Отключение DNS..."
/opt/zapretdeck/dns.sh reset
log "Очистка завершена"