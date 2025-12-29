#!/usr/bin/env bash

# Константы
BASE_DIR="$(realpath "$(dirname "$0")")"
REPO_DIR="$BASE_DIR/zapret-latest"
REPO_URL="https://github.com/Flowseal/zapret-discord-youtube"
NFQWS_PATH="$BASE_DIR/nfqws"
CONF_FILE="$BASE_DIR/conf.env"
STOP_SCRIPT="$BASE_DIR/stop_and_clean_nft.sh"
DNS_SCRIPT="$BASE_DIR/dns.sh"
LOG_FILE="$BASE_DIR/debug.log"

# Флаг отладки
DEBUG=false
NOINTERACTIVE=false

_term() {
    if [[ -x "$STOP_SCRIPT" ]]; then
        sudo /usr/bin/env bash "$STOP_SCRIPT" 2>&1 | while read -r line; do log "stop_script: $line"; done
    else
        log "Скрипт остановки $STOP_SCRIPT не найден или не исполняемый"
    fi
}
trap _term SIGINT SIGTERM EXIT

# Функция для логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Функция отладочного логирования
debug_log() {
    if $DEBUG; then
        log "[DEBUG] $1"
    fi
}

# Функция обработки ошибок
handle_error() {
    log "Ошибка: $1" >&2
    exit 1
}

# Функция для проверки наличия необходимых утилит
check_dependencies() {
    local deps=("git" "nft" "grep" "sed")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" >/dev/null 2>&1; then
            handle_error "Не установлена утилита $dep"
        fi
    done
}

# Функция чтения конфигурационного файла
load_config() {
    if ! touch "$CONF_FILE" 2>/dev/null; then
        handle_error "Нет прав на запись в $CONF_FILE"
    fi
    if [ ! -f "$CONF_FILE" ]; then
        log "Файл конфигурации $CONF_FILE не найден, создаю с значениями по умолчанию"
        interface="any"
        strategy=$(find "$REPO_DIR" -maxdepth 1 -type f -name "*.bat" | head -n 1 | xargs -n 1 basename 2>/dev/null)
        if [ -z "$strategy" ]; then
            handle_error "Не найден ни один .bat файл в $REPO_DIR"
        fi
        echo -e "interface=$interface\nstrategy=$strategy\ndns=disabled" > "$CONF_FILE"
    else
        source "$CONF_FILE"
        interface=${interface:-any}
        if [ -z "${strategy:-}" ]; then
            strategy=$(find "$REPO_DIR" -maxdepth 1 -type f -name "*.bat" | head -n 1 | xargs -n 1 basename 2>/dev/null)
            if [ -z "$strategy" ]; then
                handle_error "Не найден ни один .bat файл в $REPO_DIR, и strategy не указан"
            fi
            echo -e "interface=$interface\nstrategy=$strategy\ndns=${dns:-disabled}" > "$CONF_FILE"
        fi
    fi
    debug_log "Загружено из conf.env: interface=$interface, strategy=$strategy, dns=$dns"
}

# Функция для настройки репозитория
setup_repository() {
    if [ ! -d "$REPO_DIR" ]; then
        log "Клонирование репозитория..."
        git clone "$REPO_URL" "$REPO_DIR" 2>&1 | while read -r line; do log "git: $line"; done || handle_error "Ошибка при клонировании репозитория"
        cd "$REPO_DIR" && git checkout a609396772dfe2a3c85b0cec8c314ff9ac96a5c0 2>&1 | while read -r line; do log "git: $line"; done && cd ..
        chmod +x "$BASE_DIR/rename_bat.sh"
        rm -rf "$REPO_DIR/.git"
        "$BASE_DIR/rename_bat.sh" 2>&1 | while read -r line; do log "rename_bat: $line"; done || handle_error "Ошибка при переименовании файлов"
    else
        log "Использование существующей версии репозитория"
    fi
}

# Функция для поиска bat файлов
find_bat_files() {
    local pattern="$1"
    find "$REPO_DIR" -maxdepth 1 -type f -name "$pattern"
}

# Функция для выбора стратегии
select_strategy() {
    cd "$REPO_DIR" || handle_error "Не удалось перейти в директорию $REPO_DIR"
    
    if $NOINTERACTIVE; then
        debug_log "Неинтерактивный режим, strategy=$strategy"
        if [ ! -f "$strategy" ]; then
            handle_error "Указанный .bat файл стратегии $strategy не найден"
        fi
        parse_bat_file "$strategy"
        cd ..
        return
    fi
    
    local IFS=$'\n'
    local bat_files=($(find_bat_files "general*.bat" | xargs -n1 echo) $(find_bat_files "discord.bat" | xargs -n1 echo))
    
    if [ ${#bat_files[@]} -eq 0 ]; then
        cd ..
        handle_error "Не найдены подходящие .bat файлы"
    fi
    
    echo "Доступные стратегии:"
    for i in "${!bat_files[@]}"; do
        echo "$((i+1))) ${bat_files[i]}"
    done
    read -p "#? " choice
    if [[ "$choice" =~ ^[0-9]+$ && "$choice" -ge 1 && "$choice" -le ${#bat_files[@]} ]]; then
        strategy="${bat_files[$((choice-1))]}"
        log "Выбрана стратегия: $strategy"
        parse_bat_file "$strategy"
        cd ..
    else
        echo "Неверный выбор. Попробуйте еще раз."
        select_strategy
    fi
}

# Функция парсинга параметров из bat файла
parse_bat_file() {
    local file="$1"
    local queue_num=0
    local bin_path="bin/"
    debug_log "Parsing .bat file: $file"
    
    while IFS= read -r line; do
        debug_log "Processing line: $line"
        
        [[ "$line" =~ ^[[:space:]]*:: || -z "$line" ]] && continue
        
        line="${line//%BIN%/$bin_path}"
        line="${line//%GameFilter/}"
        
        if [[ "$line" =~ --filter-(tcp|udp)=([0-9,-]+)[[:space:]]*(.*?)(--new|$) ]]; then
            local protocol="${BASH_REMATCH[1]}"
            local ports="${BASH_REMATCH[2]}"
            local nfqws_args="${BASH_REMATCH[3]}"
            
            nfqws_args="${nfqws_args//%LISTS%/lists/}"
            
            nft_rules+=("$protocol dport {$ports} counter queue num $queue_num bypass")
            nfqws_params+=("$nfqws_args")
            debug_log "Matched protocol: $protocol, ports: $ports, queue: $queue_num"
            debug_log "NFQWS parameters for queue $queue_num: $nfqws_args"
            
            ((queue_num++))
        fi
    done < <(grep -v "^@echo" "$file" | grep -v "^chcp" | tr -d '\r')
}

# Функция настройки nftables
setup_nftables() {
    local interface="$1"
    local table_name="inet zapretunix"
    local chain_name="output"
    local rule_comment="Added by zapret script"
    
    log "Настройка nftables с очисткой только помеченных правил..."
    
    if sudo nft list tables | grep -q "$table_name"; then
        sudo nft flush chain $table_name $chain_name
        sudo nft delete chain $table_name $chain_name
        sudo nft delete table $table_name
    fi
    
    sudo nft add table $table_name
    sudo nft add chain $table_name $chain_name "{ type filter hook output priority 0; }"
    
    local oif_clause=""
    if [ -n "$interface" ] && [ "$interface" != "any" ]; then
        oif_clause="oifname \"$interface\""
    fi

    for queue_num in "${!nft_rules[@]}"; do
        sudo nft add rule $table_name $chain_name $oif_clause ${nft_rules[$queue_num]} comment \"$rule_comment\" ||
        handle_error "Ошибка при добавлении правила nftables для очереди $queue_num"
    done
}

# Функция запуска nfqws
start_nfqws() {
    log "Запуск процессов nfqws..."
    sudo pkill -f nfqws 2>/dev/null
    cd "$REPO_DIR" || handle_error "Не удалось перейти в директорию $REPO_DIR"
    for queue_num in "${!nfqws_params[@]}"; do
        debug_log "Запуск nfqws с параметрами: $NFQWS_PATH --daemon --qnum=$queue_num ${nfqws_params[$queue_num]}"
        eval "sudo $NFQWS_PATH --daemon --qnum=$queue_num ${nfqws_params[$queue_num]}" ||
        handle_error "Ошибка при запуске nfqws для очереди $queue_num"
    done
}

# Основная функция
main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -debug)
                DEBUG=true
                shift
                ;;
            -nointeractive)
                NOINTERACTIVE=true
                shift
                load_config
                ;;
            *)
                break
                ;;
        esac
    done
    
    check_dependencies
    if [ ! -d "$REPO_DIR" ]; then
        setup_repository
    fi
    
    if $NOINTERACTIVE; then
        select_strategy
        if [ "${dns:-disabled}" = "enabled" ] && [ -x "$DNS_SCRIPT" ]; then
            sudo bash "$DNS_SCRIPT" set 2>&1 | while read -r line; do log "dns.sh: $line"; done || log "Ошибка установки DNS"
        fi
        setup_nftables "$interface"
    else
        select_strategy
        local interfaces=("any" $(ls /sys/class/net 2>/dev/null | grep -v lo))
        if [ ${#interfaces[@]} -eq 0 ]; then
            handle_error "Не найдены сетевые интерфейсы"
        fi
        echo "Доступные сетевые интерфейсы:"
        select interface in "${interfaces[@]}"; do
            if [ -n "$interface" ]; then
                log "Выбран интерфейс: $interface"
                break
            fi
            echo "Неверный выбор. Попробуйте еще раз."
        done
        if [ "${dns:-disabled}" = "enabled" ] && [ -x "$DNS_SCRIPT" ]; then
            sudo bash "$DNS_SCRIPT" set 2>&1 | while read -r line; do log "dns.sh: $line"; done || log "Ошибка установки DNS"
        fi
        setup_nftables "$interface"
    fi
    start_nfqws
    log "Настройка успешно завершена"
}

# Запуск скрипта
main "$@"

sleep infinity &
wait