#!/usr/bin/env bash
set -uo pipefail

# === ПУТИ ===
BASE_DIR="/opt/zapretdeck"
REPO_DIR="$BASE_DIR/zapret-latest"
CUSTOM_DIR="$BASE_DIR/custom-strategies"
NFQWS_PATH="$BASE_DIR/nfqws"
CONF_FILE="$BASE_DIR/conf.env"
STOP_SCRIPT="$BASE_DIR/stop_and_clean_nft.sh"
LOG_FILE="$BASE_DIR/debug.log"
GAME_FILTER_PORTS="1024-65535"

nft_rules=()
nfqws_params=()

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [MAIN] $*" | tee -a "$LOG_FILE"; }

# === УЛУЧШЕННАЯ ФУНКЦИЯ АВТОПОДБОРА ===
auto_discovery() {
    log "=== Запуск расширенного автоматического подбора стратегии ==="
    # Используем google.com как лакмусовую бумажку для curl
    local test_url="https://www.google.com"
    
    # Список стратегий, включая рабочую для YouTube hostfakesplit
    local test_strats=(
        "--filter-tcp=443 --dpi-desync=hostfakesplit --dpi-desync-repeats=6 --dpi-desync-fooling=ts --dpi-desync-hostfakesplit-mod=host=www.google.com"
        "--filter-tcp=443 --dpi-desync=split2 --dpi-desync-split-pos=1 --dpi-desync-fooling=md5sig"
        "--filter-tcp=443 --dpi-desync=fake --dpi-desync-autottl=2 --dpi-desync-repeats=6"
        "--filter-tcp=443 --dpi-desync=disorder --dpi-desync-split-pos=1"
        "--filter-tcp=443 --dpi-desync=fake --dpi-desync-ttl=8"
    )

    for strat in "${test_strats[@]}"; do
        log "Тестирую вариант: $strat"
        
        # Полная очистка перед тестом
        sudo bash "$STOP_SCRIPT" >/dev/null 2>&1
        
        # Настройка минимальной таблицы для теста
        sudo nft add table inet zapretunix
        sudo nft add chain inet zapretunix output '{ type filter hook output priority 0; policy accept; }'
        sudo nft add rule inet zapretunix output tcp dport 443 counter queue num 0 bypass
        
        # Запуск nfqws
        local cmd="$NFQWS_PATH"
        [ ! -f "$cmd" ] && cmd="$REPO_DIR/bin/nfqws"
        sudo $cmd --daemon --qnum=0 $strat >/dev/null 2>&1
        
        # Пауза для инициализации сокета
        sleep 3
        
        # Проверка curl (-k игнорирует ошибки сертификатов для скорости)
        if curl -I -s -k --connect-timeout 8 "$test_url" > /dev/null; then
            log ">>> УСПЕХ! Стратегия найдена: $strat"
            
            # Сохраняем результат
            echo "@echo off" > "$CUSTOM_DIR/auto_found.bat"
            echo ":: Автоматически подобрано $(date)" >> "$CUSTOM_DIR/auto_found.bat"
            echo "$strat" >> "$CUSTOM_DIR/auto_found.bat"
            
            # Прописываем в конфиг
            sed -i "s/^strategy=.*/strategy=auto_found.bat/" "$CONF_FILE"
            
            sudo bash "$STOP_SCRIPT" >/dev/null 2>&1
            return 0
        fi
        log "Результат: не работает."
    done

    log "КРИТИЧЕСКАЯ ОШИБКА: Ни одна стратегия не подошла."
    return 1
}

parse_bat_file() {
    local file="$1"
    local q=0
    log "Начинаю разбор файла: $file"

    local content
    content=$(tr -d '\r\000' < "$file" | sed ':a; /^[ \t]*^/ { N; s/\n[ \t]*\^//; ba }' | sed 's/--new/\n/g')

    while read -r line; do
        [[ "$line" =~ ^[[:space:]]*:: ]] && continue
        [[ ! "$line" =~ "--filter-" ]] && continue
        
        line="${line//%BIN%/$REPO_DIR/bin/}"
        line="${line//%LISTS%/$REPO_DIR/lists/}"
        line="${line//\\//}"
        
        if [[ "${gamefilter:-}" == "true" ]]; then
            line="${line//%GameFilter%/$GAME_FILTER_PORTS}"
        else
            line=$(echo "$line" | sed -E 's/%GameFilter%//g; s/,,+/,/g; s/,([[:space:]])/\1/g; s/=[,]+/=/g')
        fi

        if [[ "$line" =~ --filter-(tcp|udp)=([0-9,-]+) ]]; then
            local proto="${BASH_REMATCH[1]}"
            local ports="${BASH_REMATCH[2]}"
            ports=$(echo "$ports" | sed 's/,$//; s/^,//')
            
            local args
            args=$(echo "$line" | sed -E "s/--filter-$proto=[0-9,-]+//; s/\"//g; s/ - / /g" | xargs)
            
            if [[ -n "$ports" ]]; then
                nft_rules+=("$proto dport {$ports} counter queue num $q bypass")
                nfqws_params+=("$args")
                log "-> Очередь $q: $proto/[$ports]"
                ((q++))
            fi
        fi
    done <<< "$content"
}

main() {
    if [[ "${1:-}" == "auto" ]]; then
        auto_discovery
        exit $?
    fi

    log "------------------------------------------------"
    log "Запуск ZapretDeck"
    
    if [ ! -f "$CONF_FILE" ]; then log "ОШИБКА: Конфиг не найден"; exit 1; fi
    source "$CONF_FILE"
    
    log "Очистка nftables..."
    sudo bash "$STOP_SCRIPT" || true

    local strat_path="$REPO_DIR/$strategy"
    [[ ! -f "$strat_path" ]] && strat_path="$CUSTOM_DIR/$strategy"
    
    # Если стратегия = auto_found.bat, но файла нет - запускаем автоподбор
    if [[ "$strategy" == "auto_found.bat" && ! -f "$strat_path" ]]; then
        log "Стратегия auto_found.bat не найдена, запускаю автоподбор..."
        if auto_discovery; then
            # После успешного автоподбора перезагружаем конфиг и продолжаем
            source "$CONF_FILE"
            strat_path="$CUSTOM_DIR/$strategy"
        else
            log "КРИТИЧЕСКАЯ ОШИБКА: Автоподбор не удался"
            exit 1
        fi
    fi
    
    if [[ ! -f "$strat_path" ]]; then
        log "ОШИБКА: Файл стратегии не найден: $strategy"
        exit 1
    fi

    parse_bat_file "$strat_path"

    if [ ${#nft_rules[@]} -eq 0 ]; then
        log "КРИТИЧЕСКАЯ ОШИБКА: Не удалось распарсить ни одной очереди!"
        exit 1
    fi

    log "Применение правил nftables..."
    local table="inet zapretunix"
    sudo nft add table $table
    sudo nft add chain $table output '{ type filter hook output priority 0; policy accept; }'
    
    local dev_cond=""
    [[ -n "${interface:-}" && "$interface" != "any" ]] && dev_cond="oifname \"$interface\""

    for i in "${!nft_rules[@]}"; do
        sudo nft add rule $table output $dev_cond ${nft_rules[$i]} comment "zapretdeck"
    done

    log "Запуск процессов nfqws..."
    cd "$REPO_DIR/bin" || cd "$REPO_DIR"

    for i in "${!nfqws_params[@]}"; do
        log "Q$i: запуск..."
        local cmd="$NFQWS_PATH"
        [ ! -f "$cmd" ] && cmd="$REPO_DIR/bin/nfqws"
        eval "sudo $cmd --daemon --qnum=$i ${nfqws_params[$i]}" >> "$LOG_FILE" 2>&1
    done

    log "Готово. Работает очередей: ${#nft_rules[@]}"
    sleep infinity
}

main "$@"