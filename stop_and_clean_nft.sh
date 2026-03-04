#!/usr/bin/env bash

set -e

# === ПУТИ И КОНСТАНТЫ ===
# Determine BASE_DIR dynamically
if [[ -n "${HOME:-}" && -d "$HOME/zapretdeck" ]]; then
    BASE_DIR="$HOME/zapretdeck"
else
    BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
LOG_FILE="$BASE_DIR/debug.log"
NFQWS_BIN="$BASE_DIR/nfqws"

# Константы из стабильной версии
TABLE_NAME="inet zapretunix"
CHAIN_NAME="output"
RULE_COMMENT="Added by zapret script"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [STOP] $*" | tee -a "$LOG_FILE"
}

log "=== Запуск очистки ZapretDeck ==="

# 1. Остановка процессов nfqws (ROBUST VERSION FROM ZAPRETDECK)
stop_nfqws() {
    log "Поиск и остановка nfqws..."
    # Убиваем по имени бинарника и по полному пути
    sudo pkill -f "nfqws" >/dev/null 2>&1 || true
    sudo pkill -f "$NFQWS_BIN" >/dev/null 2>&1 || true
    
    # Краткая пауза
    sleep 0.5
    
    # Если кто-то выжил — добиваем жестко
    if pgrep -f "nfqws" >/dev/null 2>&1; then
        log "Принудительное завершение зависших процессов nfqws..."
        sudo pkill -9 -f "nfqws" >/dev/null 2>&1 || true
    fi
}

# 2. Очистка nftables (STABLE LOGIC)
clear_nftables() {
    log "Очистка правил nftables..."
    
    # Проверка на существование таблицы
    if sudo nft list tables | grep -q "$TABLE_NAME"; then
        # Проверка на существование цепочки
        if sudo nft list chain $TABLE_NAME $CHAIN_NAME >/dev/null 2>&1; then
            # Получаем все handle значений правил с меткой, добавленных скриптом
            # Используем sudo nft -a list chain ...
            handles=$(sudo nft -a list chain $TABLE_NAME $CHAIN_NAME | grep "$RULE_COMMENT" | awk '{print $NF}')
            
            # Удаление каждого правила по handle значению
            for handle in $handles; do
                sudo nft delete rule $TABLE_NAME $CHAIN_NAME handle $handle 2>/dev/null || \
                log "Не удалось удалить правило с handle $handle"
            done
            
            # Пытаемся удалить цепочку и таблицу (если они пусты)
            sudo nft delete chain $TABLE_NAME $CHAIN_NAME 2>/dev/null || true
            sudo nft delete table $TABLE_NAME 2>/dev/null || true
            
            log "Правила очищены."
        else
            log "Цепочка $CHAIN_NAME не найдена в таблице $TABLE_NAME. Возможно, уже очищена."
            # Попробуем удалить таблицу целиком, если она пустая
             sudo nft delete table $TABLE_NAME 2>/dev/null || true
        fi
    else
        log "Таблица $TABLE_NAME не найдена. Нечего очищать."
    fi
}

# 3. Отключение WARP
disconnect_warp() {
    if command -v warp-cli >/dev/null 2>&1; then
        log "Отключение WARP..."
        warp-cli disconnect >/dev/null 2>&1 || true
    fi
}

# --- ВЫПОЛНЕНИЕ ---
stop_nfqws
clear_nftables
disconnect_warp

log "=== Очистка завершена ==="
echo "------------------------------------------------" >> "$LOG_FILE"