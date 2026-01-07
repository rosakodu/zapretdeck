#!/usr/bin/env bash
set -euo pipefail

# === Автоматическое определение BASE_DIR ===
if [[ -f "/opt/zapretdeck/zapret_gui.py" ]]; then
    BASE_DIR="/opt/zapretdeck"
else
    BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

TARGET_DIRS=("${BASE_DIR}/custom-strategies" "${BASE_DIR}/zapret-latest")  # Для обоих
LOG_FILE="${BASE_DIR}/debug.log"

# === Логирование ===
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [RENAME] $*" | tee -a "$LOG_FILE"
}

# Транслитерация (ваша + чужая)
transliterate() {
    local name="$1"
    name=$(echo "$name" | sed \
        -e 's/а/a/g' -e 's/б/b/g' -e 's/в/v/g' -e 's/г/g/g' \
        -e 's/д/d/g' -e 's/е/e/g' -e 's/ё/yo/g' -e 's/ж/zh/g' \
        -e 's/з/z/g' -e 's/и/i/g' -e 's/й/y/g' -e 's/к/k/g' \
        -e 's/л/l/g' -e 's/м/m/g' -e 's/н/n/g' -e 's/о/o/g' \
        -e 's/п/p/g' -e 's/р/r/g' -e 's/с/s/g' -e 's/т/t/g' \
        -e 's/у/u/g' -e 's/ф/f/g' -e 's/х/h/g' -e 's/ц/ts/g' \
        -e 's/ч/ch/g' -e 's/ш/sh/g' -e 's/щ/sch/g' -e 's/ъ//g' \
        -e 's/ы/y/g' -e 's/ь//g' -e 's/э/e/g' -e 's/ю/yu/g' \
        -e 's/я/ya/g' \
        -e 's/А/A/g' -e 's/Б/B/g' -e 's/В/V/g' -e 's/Г/G/g' \
        -e 's/Д/D/g' -e 's/Е/E/g' -e 's/Ё/Yo/g' -e 's/Ж/Zh/g' \
        -e 's/З/Z/g' -e 's/И/I/g' -e 's/Й/Y/g' -e 's/К/K/g' \
        -e 's/Л/L/g' -e 's/М/M/g' -e 's/Н/N/g' -e 's/О/O/g' \
        -e 's/П/P/g' -e 's/Р/R/g' -e 's/С/S/g' -e 's/Т/T/g' \
        -e 's/У/U/g' -e 's/Ф/F/g' -e 's/Х/H/g' -e 's/Ц/Ts/g' \
        -e 's/Ч/Ch/g' -e 's/Ш/Sh/g' -e 's/Щ/Sch/g' -e 's/Ъ//g' \
        -e 's/Ы/Y/g' -e 's/Ь//g' -e 's/Э/E/g' -e 's/Ю/Yu/g' \
        -e 's/Я/Ya/g')
    echo "$name"
}

# Очистка имени (чужая + ваша)
sanitize_name() {
    local name="$1"
    name=$(echo "$name" | tr '[:upper:]' '[:lower:]')
    name=$(echo "$name" | sed -e 's/[[:space:]()[\]{}+-]/_/g' -e 's/[!@#\$%^&*='"'"'<>?\\|]/_/g')
    name=$(echo "$name" | sed -e 's/^_\+//' -e 's/_\+$//')
    name=$(echo "$name" | sed -e 's/_\+/_/g')
    name=$(echo "$name" | sed -e 's/_\+\.bat$/.bat/')
    echo "$name"
}

# Основная логика (для всех TARGET_DIRS)
main() {
    local renamed_count=0
    for dir in "${TARGET_DIRS[@]}"; do
        if [[ ! -d "$dir" ]]; then
            log "Папка $dir не найдена — пропуск"
            continue
        fi

        if ! ls "$dir"/*.bat >/dev/null 2>&1; then
            log "Нет .bat файлов в $dir — пропуск"
            continue
        fi

        log "Запуск переименования .bat файлов в $dir"

        find "$dir" -maxdepth 1 -type f -name "*.bat" | while read -r file; do
            local old_name=$(basename "$file")
            local file_dir=$(dirname "$file")

            # Пропускаем нормальные имена
            if [[ "$old_name" =~ ^[a-zA-Z0-9_-]+\.bat$ ]]; then
                continue
            fi

            local new_name=$(transliterate "$old_name")
            new_name=$(sanitize_name "$new_name")

            if [[ "$old_name" == "$new_name" ]]; then
                continue
            fi

            local final_name="$new_name"
            local counter=1
            local base="${new_name%.bat}"
            while [[ -f "$file_dir/$final_name" ]]; do
                final_name="${base}_${counter}.bat"
                ((counter++))
            done

            if mv "$file" "$file_dir/$final_name" 2>>"$LOG_FILE"; then
                log "Переименовано: '$old_name' → '$final_name' в $dir"
                ((renamed_count++))
            else
                log "ОШИБКА: не удалось переименовать '$old_name' в $dir"
            fi
        done
    done

    if [[ $renamed_count -eq 0 ]]; then
        log "Нет файлов для переименования (все .bat уже в правильном формате)"
    else
        log "Переименование завершено: обработано $renamed_count файлов"
    fi
}

main "$@"
exit 0