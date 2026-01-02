#!/usr/bin/env bash
set -euo pipefail

# === ПУТИ И КОНСТАНТЫ ===
BASE_DIR="/opt/zapretdeck"
LOG_FILE="$BASE_DIR/debug.log"
NFQWS_BIN="$BASE_DIR/nfqws"

# Массив таблиц для проверки (чистим и свои, и "чужие" на всякий случай)
TABLES_TO_CLEAN=("inet zapret" "inet zapretunix")
# Ключевые слова в комментариях для поиска handle
COMMENTS_TO_CLEAN=("ZapretDeck" "Added by zapret script")

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [STOP] $*" | tee -a "$LOG_FILE"
}

log "=== Запуск полной очистки ZapretDeck ==="

# 1. Остановка процессов nfqws
stop_nfqws() {
    log "Поиск и остановка nfqws..."
    # Убиваем по имени бинарника и по полному пути
    sudo pkill -f "nfqws" >/dev/null 2>&1 || true
    sudo pkill -f "$NFQWS_BIN" >/dev/null 2>&1 || true
    
    sleep 1
    
    # Если кто-то выжил — добиваем жестко
    if pgrep -f "nfqws" >/dev/null 2>&1; then
        log "Принудительное завершение зависших процессов nfqws..."
        sudo pkill -9 -f "nfqws" >/dev/null 2>&1 || true
    fi
}

# 2. Очистка nftables
clear_nftables() {
    for table in "${TABLES_TO_CLEAN[@]}"; do
        if sudo nft list tables | grep -q "$table"; then
            log "Найдена таблица $table. Начинаю удаление..."
            
            # 1. Сначала пробуем удалить правила по комментариям (если таблица общая)
            for comment in "${COMMENTS_TO_CLEAN[@]}"; do
                # Ищем все handle правил с этим комментарием во всех цепочках таблицы
                handles=$(sudo nft -a list table $table 2>/dev/null | grep -i "$comment" | awk '{print $NF}' || true)
                for handle in $handles; do
                    # Пытаемся определить имя цепочки для этого handle
                    chain=$(sudo nft -a list table $table | grep -B 1 "handle $handle" | grep "chain" | awk '{print $2}' | head -n 1 || echo "output")
                    sudo nft delete rule $table $chain handle "$handle" 2>/dev/null || true
                done
            done

            # 2. Пытаемся снести таблицу целиком (самый надежный способ)
            sudo nft flush table "$table" 2>/dev/null || true
            sudo nft delete table "$table" 2>/dev/null || true
            
            log "Таблица $table успешно удалена или очищена."
        fi
    done
}

# --- ВЫПОЛНЕНИЕ ---
stop_nfqws
clear_nftables

log "=== Очистка завершена успешно ==="
echo "------------------------------------------------" >> "$LOG_FILE"