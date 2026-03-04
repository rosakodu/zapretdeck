#!/usr/bin/env bash

set -e

# === ПУТИ ===
# Determine BASE_DIR dynamically - use $HOME/zapretdeck or script location
if [[ -n "${HOME:-}" && -d "$HOME/zapretdeck" ]]; then
    BASE_DIR="$HOME/zapretdeck"
else
    BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
REPO_DIR="$BASE_DIR/zapret-latest"
CUSTOM_DIR="$BASE_DIR/custom-strategies"
NFQWS_PATH="$BASE_DIR/nfqws"
CONF_FILE="$BASE_DIR/conf.env"
STOP_SCRIPT="$BASE_DIR/stop_and_clean_nft.sh"
LOG_FILE="$BASE_DIR/debug.log"
MAIN_REPO_REV="7e723f0a3f7185af1425b93938a56401a1e6b286"

# Флаг отладки
DEBUG=false
NOINTERACTIVE=true # Default to non-interactive for GUI usage

# GameFilter
GAME_FILTER_PORTS="1024-65535"
USE_GAME_FILTER=false

# Arrays for nfqws parameters
nfqws_params=()
tcp_ports=""
udp_ports=""

_term() {
    sudo /usr/bin/env bash "$STOP_SCRIPT"
}

# Функция для логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [MAIN] $*" | tee -a "$LOG_FILE"
}

# Функция отладочного логирования
debug_log() {
    if $DEBUG; then
        echo "[DEBUG] $1" | tee -a "$LOG_FILE"
    fi
}

# Функция обработки ошибок
handle_error() {
    log "Ошибка: $1"
    exit 1
}

# Функция чтения конфигурационного файла
load_config() {
    if [ ! -f "$CONF_FILE" ]; then
        handle_error "Файл конфигурации $CONF_FILE не найден"
    fi

    # Чтение переменных из конфигурационного файла
    source "$CONF_FILE"
}

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
        # Используем ту же очередь 220, что и в основном скрипте сейчас, или 0 как было?
        # Стабильный скрипт использует 220. Будем использовать 220 для консистентности.
        local queue_num=220
        
        sudo nft add table inet zapretunix
        sudo nft add chain inet zapretunix output '{ type filter hook output priority 0; policy accept; }'
        sudo nft add rule inet zapretunix output tcp dport 443 counter queue num $queue_num bypass
        
        # Запуск nfqws
        local cmd="$NFQWS_PATH"
        [ ! -f "$cmd" ] && cmd="$REPO_DIR/bin/nfqws"
        sudo $cmd --daemon --qnum=$queue_num $strat >/dev/null 2>&1
        
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

# Функция парсинга параметров из bat файла (СТАБИЛЬНАЯ ВЕРСИЯ)
parse_bat_file() {
    local file="$1"
    local bin_path="bin/"
    debug_log "Parsing .bat file: $file"

    if [ ! -f "$file" ]; then
        handle_error "Файл стратегии не найден: $file"
    fi

    # Читаем весь файл целиком
    local content=$(cat "$file" | tr -d '\r')

    debug_log "File content loaded"

    # Заменяем переменные
    content="${content//%BIN%/$bin_path}"
    content="${content//%LISTS%/lists/}"

    # Обрабатываем GameFilter
    if [ "$USE_GAME_FILTER" = true ]; then
        content="${content//%GameFilter%/$GAME_FILTER_PORTS}"
    else
        content="${content//,%GameFilter%/}"
        content="${content//%GameFilter%,/}"
    fi

    # Ищем --wf-tcp и --wf-udp
    local wf_tcp_count=$(echo "$content" | grep -oP -- '--wf-tcp=' | wc -l)
    local wf_udp_count=$(echo "$content" | grep -oP -- '--wf-udp=' | wc -l)
    
    # Если нет явных --wf-tcp/udp, попробуем поискать старый формат --filter-tcp/udp
    # Но стабильный скрипт использует --wf-tcp/udp как маркеры.
    # ZapretDeck стратегии (custom) могут использовать --filter.
    # Давайте поддержим оба варианта.

    # Пытаемся извлечь порты через --wf-tcp (как в стабильном)
    tcp_ports=$(echo "$content" | grep -oP -- '--wf-tcp=\K[0-9,-]+' | head -n1)
    udp_ports=$(echo "$content" | grep -oP -- '--wf-udp=\K[0-9,-]+' | head -n1)

    # Если пусто, пробуем через --filter-tcp/udp (legacy ZapretDeck способ)
    if [ -z "$tcp_ports" ] && [ -z "$udp_ports" ]; then
         debug_log "No --wf-* params found, trying legacy --filter-*"
    fi
    
    # Парсим с помощью grep -oP (Perl regex) для извлечения аргументов nfqws
    # Стабильный скрипт ожидает: --filter-tcp=PORTS ARGS
    
    while IFS= read -r match; do
        if [[ "$match" =~ --filter-(tcp|udp)=([0-9,%-]+)[[:space:]]+(.*) ]]; then
            local protocol="${BASH_REMATCH[1]}"
            local ports="${BASH_REMATCH[2]}"
            local nfqws_args="${BASH_REMATCH[3]}"

            # Удаляем --new в конце если есть
            # nfqws_args="${nfqws_args%% --new*}" # В оригинале закомментировано

            # Очищаем лишние пробелы
            nfqws_args=$(echo "$match" | xargs)
            nfqws_args="${nfqws_args//=^!/=!}"

            nfqws_params+=("$nfqws_args")
            
            # Если порты не были найдены через --wf, возьмем их отсюда
            if [ "$protocol" == "tcp" ] && [ -z "$tcp_ports" ]; then
                tcp_ports="$ports"
            fi
            if [ "$protocol" == "udp" ] && [ -z "$udp_ports" ]; then
                udp_ports="$ports"
            fi
            
            debug_log "Matched protocol: $protocol, ports: $ports"
            debug_log "NFQWS parameters: $nfqws_args"
        fi
    done < <(echo "$content" | grep -oP -- '--filter-(tcp|udp)=([0-9,-]+)\s+(?:[\s\S]*?--new|.*)')
}

# Обновленная функция настройки nftables с метками (СТАБИЛЬНАЯ ВЕРСИЯ)
setup_nftables() {
    local interface="$1"
    local table_name="inet zapretunix"
    local chain_name="output"
    local rule_comment="Added by zapret script"
    local queue_num=220

    log "Настройка nftables с очисткой только помеченных правил..."

    # Удаляем существующую таблицу, если она была создана этим скриптом
    if sudo nft list tables | grep -q "$table_name"; then
        sudo nft flush chain $table_name $chain_name 2>/dev/null || true
        sudo nft delete chain $table_name $chain_name 2>/dev/null || true
        sudo nft delete table $table_name 2>/dev/null || true
    fi

    # Добавляем таблицу и цепочку
    sudo nft add table $table_name
    sudo nft add chain $table_name $chain_name { type filter hook output priority 0\; }

    local oif_clause=""
    if [ -n "$interface" ] && [ "$interface" != "any" ]; then
        oif_clause="oifname \"$interface\""
    fi

    # Добавляем правило для TCP портов (если есть)
    if [ -n "$tcp_ports" ]; then
        # Очистка портов от возможных мусорных символов
        tcp_ports=$(echo "$tcp_ports" | sed 's/,$//; s/^,//')
        
        sudo nft add rule $table_name $chain_name $oif_clause meta mark != 0x40000000 tcp dport {$tcp_ports} counter queue num $queue_num bypass comment \"$rule_comment\" ||
            handle_error "Ошибка при добавлении TCP правила nftables: $tcp_ports"
        log "Добавлено TCP правило для портов: $tcp_ports -> queue $queue_num"
    fi

    # Добавляем правило для UDP портов (если есть)
    if [ -n "$udp_ports" ]; then
        udp_ports=$(echo "$udp_ports" | sed 's/,$//; s/^,//')
        
        sudo nft add rule $table_name $chain_name $oif_clause meta mark != 0x40000000 udp dport {$udp_ports} counter queue num $queue_num bypass comment \"$rule_comment\" ||
            handle_error "Ошибка при добавлении UDP правила nftables: $udp_ports"
        log "Добавлено UDP правило для портов: $udp_ports -> queue $queue_num"
    fi
}

# Функция запуска nfqws (СТАБИЛЬНАЯ ВЕРСИЯ)
start_nfqws() {
    log "Запуск процесса nfqws..."
    sudo pkill -f nfqws || true
    
    # Ensure binary exists
    local cmd="$NFQWS_PATH"
    if [ ! -f "$cmd" ]; then
        # Try finding it in repo bin
        cmd="$REPO_DIR/bin/nfqws"
    fi
    
    if [ ! -f "$cmd" ]; then
         handle_error "nfqws не найден по пути $NFQWS_PATH или $REPO_DIR/bin/nfqws"
    fi

    cd "$REPO_DIR" || handle_error "Не удалось перейти в директорию $REPO_DIR"

    # Собираем все параметры в одну строку, так как стабильный скрипт запускает один инстанс
    # Или несколько?
    # В стабильном скрипте:
    # full_params=""
    # for params in "${nfqws_params[@]}"; do full_params="$full_params $params"; done
    # eval "sudo $NFQWS_PATH ... $full_params"
    
    local full_params=""
    for params in "${nfqws_params[@]}"; do
        full_params="$full_params $params"
    done

    if [ -z "$full_params" ]; then
        handle_error "Не найдены параметры для запуска nfqws (пустая стратегия?)"
    fi

    debug_log "Запуск nfqws с параметрами: $cmd --daemon --dpi-desync-fwmark=0x40000000 --qnum=220 $full_params"
    eval "sudo $cmd --daemon --dpi-desync-fwmark=0x40000000 --qnum=220 $full_params" ||
        handle_error "Ошибка при запуске nfqws"
}

# Основная функция
main() {
    if [[ "${1:-}" == "auto" ]]; then
        auto_discovery
        exit $?
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
        -debug)
            DEBUG=true
            shift
            ;;
        *)
            break
            ;;
        esac
    done
    
    log "------------------------------------------------"
    log "Запуск ZapretDeck (Stable Logic)"

    load_config

    # Включение GameFilter
    if [ "$gamefilter" == "true" ]; then
        USE_GAME_FILTER=true
        log "GameFilter включен"
    else
        USE_GAME_FILTER=false
        log "GameFilter выключен"
    fi
    
    # Очистка
    _term

    # Стратегия
    local strat_path="$REPO_DIR/$strategy"
    [[ ! -f "$strat_path" ]] && strat_path="$CUSTOM_DIR/$strategy"

    # Auto logic integration
    if [[ "$strategy" == "auto_found.bat" && ! -f "$strat_path" ]]; then
        log "Стратегия auto_found.bat не найдена, запускаю автоподбор..."
        if auto_discovery; then
            load_config
            strat_path="$CUSTOM_DIR/$strategy"
        else
            handle_error "Автоподбор не удался"
        fi
    fi
    
    if [[ ! -f "$strat_path" ]]; then
         # Fallback search if path is relative
         if [ -f "$REPO_DIR/$strategy" ]; then
             strat_path="$REPO_DIR/$strategy"
         elif [ -f "$CUSTOM_DIR/$strategy" ]; then
             strat_path="$CUSTOM_DIR/$strategy"
         else
             handle_error "Файл стратегии не найден: $strategy"
         fi
    fi
    
    log "Использую стратегию: $strat_path"

    parse_bat_file "$strat_path"
    setup_nftables "$interface"
    start_nfqws
    
    log "Настройка успешно завершена"
    
    # Keep alive if not daemonized by service wrapper? 
    # The stable script has sleep infinity at the end.
    sleep infinity
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi