#!/bin/bash

# Вывод ASCII-арта
cat << 'EOF'
                                   `########|:.
                                     `##########*_.
                                       '^:]v######*l
                                  .'```'..  `1######\.
                               .^,,,,,,"""^'  `u#####|
                              `,,,,,,,""""""^. .v#####,
                             `,,,,,,,""""""""^  :#####t
                            .Steam Deck Россия. '#####*
                             ^,,,,,""""""""^^^  ^#####u
                             .",,,""""""""^^^'  |#####+
                               `,""""""""^^^.  -#####z.
                                 '`^"""^`'.  ^r#####*`
                                          .`>п####ААj'
                                       '(окак######z!
                                     `#########r;.
                                         `####/м?,'
EOF

# Проверка прав sudo
if ! sudo -n true 2>/dev/null; then
    echo "Этот скрипт требует прав sudo. Пожалуйста, введите пароль."
    sudo true || { echo "Ошибка: Неверный пароль sudo или отсутствие прав."; exit 1; }
fi

# Проверка и переключение режима файловой системы SteamOS
if command -v steamos-readonly >/dev/null 2>&1; then
    echo "Проверка режима файловой системы SteamOS..."
    if mount | grep "on / type" | grep -q "ro,"; then
        echo "Файловая система в режиме только для чтения. Переключаем в режим записи..."
        sudo steamos-readonly disable || { echo "Ошибка: Не удалось отключить режим только для чтения."; exit 1; }
        readonly_was_enabled=true
    else
        readonly_was_enabled=false
    fi
else
    echo "Команда steamos-readonly не найдена. Предполагается, что это не SteamOS или режим не требуется."
    readonly_was_enabled=false
fi

# Установка TEMP_DIR как текущей директории
TEMP_DIR="$(pwd)"

# Проверка наличия необходимых файлов
required_files=("main_script.sh" "stop_and_clean_nft.sh" "dns.sh" "zapret_gui.py" "zapret-latest" "zapretdeck.desktop" "version.txt" "zapretdeck.png")
for file in "${required_files[@]}"; do
    if [ ! -e "$TEMP_DIR/$file" ]; then
        echo "Ошибка: Файл или директория '$file' не найдены в текущей директории"
        exit 1
    fi
done

# Создание requirements.txt, если отсутствует
if [ ! -f "$TEMP_DIR/requirements.txt" ]; then
    echo "Создаём requirements.txt с необходимыми Python-модулями..."
    cat > "$TEMP_DIR/requirements.txt" << EOF
customtkinter
requests
EOF
fi

# Проверка системных зависимостей
dependencies=("bash" "sed" "grep" "awk" "nftables" "python3" "python-pip" "networkmanager" "iproute2" "curl" "git")
for dep in "${dependencies[@]}"; do
    if ! command -v "$dep" &>/dev/null; then
        echo "Установка зависимости: $dep"
        sudo pacman -S --noconfirm --needed "$dep" || { echo "Ошибка: Не удалось установить $dep. Проверьте подключение к интернету или репозитории."; exit 1; }
    fi
done

# Очистка предыдущей установки
echo "Очистка предыдущей установки..."
sudo rm -rf /opt/zapretdeck
sudo rm -f /usr/local/bin/zapretdeck
sudo rm -f /usr/share/applications/zapretdeck.desktop
sudo systemctl disable --now zapret_discord_youtube >/dev/null 2>&1
sudo rm -f /etc/systemd/system/zapret_discord_youtube.service
sudo systemctl daemon-reload

# Копирование файлов
echo "Копирование файлов в /opt/zapretdeck..."
sudo mkdir -p /opt/zapretdeck || { echo "Ошибка: Не удалось создать /opt/zapretdeck"; exit 1; }
sudo chmod 755 /opt/zapretdeck
sudo cp -r "$TEMP_DIR/"* /opt/zapretdeck/
sudo chmod +x /opt/zapretdeck/main_script.sh
sudo chmod +x /opt/zapretdeck/stop_and_clean_nft.sh
sudo chmod +x /opt/zapretdeck/dns.sh
sudo chmod +x /opt/zapretdeck/zapret-latest/nfqws
sudo chmod 644 /opt/zapretdeck/zapretdeck.png
sudo chmod 644 /opt/zapretdeck/requirements.txt

# Создание файла конфигурации
echo "Создание файла конфигурации /opt/zapretdeck/conf.env..."
sudo bash -c "cat > /opt/zapretdeck/conf.env" << EOF
interface=any
auto_update=false
strategy=general_alt2.bat
dns=enabled
EOF
sudo chmod 666 /opt/zapretdeck/conf.env
sudo chown $(whoami):$(whoami) /opt/zapretdeck/conf.env

# Создание version.txt
echo "Создание version.txt..."
sudo bash -c "echo '0.0.1' > /opt/zapretdeck/version.txt"
sudo chmod 644 /opt/zapretdeck/version.txt

# Создание виртуального окружения и установка Python-зависимостей
echo "Создание виртуального окружения и установка Python-зависимостей..."
sudo python3 -m venv /opt/zapretdeck/venv || { echo "Ошибка: Не удалось создать виртуальное окружение."; exit 1; }
sudo /opt/zapretdeck/venv/bin/pip install --upgrade pip || { echo "Ошибка: Не удалось обновить pip."; exit 1; }
sudo /opt/zapretdeck/venv/bin/pip install -r /opt/zapretdeck/requirements.txt
if [ $? -ne 0 ]; then
    echo "Ошибка: Не удалось установить Python-зависимости. Проверьте подключение к интернету или содержимое requirements.txt."
    echo "Содержимое requirements.txt:"
    cat /opt/zapretdeck/requirements.txt
    exit 1
fi

# Создание сервиса
echo "Создание systemd-сервиса..."
sudo bash -c "cat > /etc/systemd/system/zapret_discord_youtube.service" << EOF
[Unit]
Description=Zapret Discord/YouTube
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/zapretdeck
User=root
EnvironmentFile=/opt/zapretdeck/conf.env
ExecStart=/usr/bin/env bash /opt/zapretdeck/main_script.sh -nointeractive
ExecStop=/usr/bin/env bash /opt/zapretdeck/stop_and_clean_nft.sh
ExecStopPost=/usr/bin/env echo "Сервис завершён"
StandardOutput=append:/opt/zapretdeck/debug.log
StandardError=append:/opt/zapretdeck/debug.log

[Install]
WantedBy=multi-user.target
EOF

# Создание .desktop файла
echo "Создание .desktop файла для меню приложений..."
sudo bash -c "cat > /usr/share/applications/zapretdeck.desktop" << EOF
[Desktop Entry]
Name=ZapretDeck
Exec=/usr/local/bin/zapretdeck
Type=Application
Terminal=false
Icon=/opt/zapretdeck/zapretdeck.png
Categories=Network;Utility;
Comment=Обход блокировок
EOF

# Создание символической ссылки для команды zapretdeck
echo "Создание команды zapretdeck..."
sudo bash -c "echo -e '#!/bin/bash\n/opt/zapretdeck/venv/bin/python3 /opt/zapretdeck/zapret_gui.py' > /usr/local/bin/zapretdeck"
sudo chmod +x /usr/local/bin/zapretdeck

# Настройка прав на лог
echo "Настройка прав на лог-файл..."
sudo touch /opt/zapretdeck/debug.log
sudo chmod 666 /opt/zapretdeck/debug.log

# Активация сервиса
echo "Активация systemd-сервиса..."
sudo systemctl daemon-reload
sudo systemctl enable zapret_discord_youtube
sudo systemctl start zapret_discord_youtube
if [ $? -ne 0 ]; then
    echo "Ошибка: Не удалось запустить сервис. Проверьте логи: systemctl status zapret_discord_youtube"
    exit 1
fi

# Возвращение файловой системы в режим только для чтения, если он был отключён
if [ "$readonly_was_enabled" = true ]; then
    echo "Возвращение файловой системы SteamOS в режим только для чтения..."
    sudo steamos-readonly enable || { echo "Ошибка: Не удалось включить режим только для чтения."; exit 1; }
fi

echo "Установка завершена. Запустите GUI с помощью команды 'zapretdeck' или из меню приложений."
