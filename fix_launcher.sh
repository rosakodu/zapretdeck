#!/bin/bash
# Скрипт для исправления проблемы с запуском ZapretDeck
# Исправляет старые скрипты запуска с путями к venv

set -e

echo -e "\033[1;34m=== ZapretDeck Launcher Fix ===\033[0m"
echo

# Определение домашнего каталога пользователя
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

echo -e "\033[1;37mИсправление скрипта запуска...\033[0m"

# Удаляем старые скрипты
rm -f "$REAL_HOME/.local/bin/zapretdeck" 2>/dev/null || true
rm -f /usr/local/bin/zapretdeck 2>/dev/null || true
rm -f /usr/bin/zapretdeck 2>/dev/null || true

# Создаём новый правильный скрипт запуска
mkdir -p "$REAL_HOME/.local/bin"
cat > "$REAL_HOME/.local/bin/zapretdeck" << 'EOF'
#!/bin/bash
# ZapretDeck launcher script
cd "$HOME/zapretdeck"
exec python3 main.py "$@"
EOF

chmod +x "$REAL_HOME/.local/bin/zapretdeck"

echo -e "\033[1;32m✓ Скрипт запуска исправлен\033[0m"
echo
echo -e "\033[1;37mНовый скрипт запуска:\033[0m $REAL_HOME/.local/bin/zapretdeck"
echo
echo -e "\033[1;33mЕсли команда zapretdeck не работает, выполните:\033[0m"
echo -e "  source ~/.bashrc && zapretdeck"
echo
echo -e "\033[1;33mИли запустите напрямую:\033[0m"
echo -e "  $REAL_HOME/.local/bin/zapretdeck"
