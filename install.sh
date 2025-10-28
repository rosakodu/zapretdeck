#!/bin/bash

# Вывод ASCII-арта
cat << 'EOF'
███████╗ █████╗ ██████╗ ██████╗ ███████╗████████╗    ██████╗ ███████╗ ██████╗██╗  ██╗    ██╗   ██╗ ██████╗     ██████╗    ███████╗
╚══███╔╝██╔══██╗██╔══██╗██╔══██╗██╔════╝╚══██╔══╝    ██╔══██╗██╔════╝██╔════╝██║ ██╔╝    ██║   ██║██╔═████╗   ██╔═████╗   ██╔════╝
  ███╔╝ ███████║██████╔╝██████╔╝█████╗     ██║       ██║  ██║█████╗  ██║     █████╔╝     ██║   ██║██║██╔██║   ██║██╔██║   ███████╗
 ███╔╝  ██╔══██║██╔═══╝ ██╔══██╗██╔══╝     ██║       ██║  ██║██╔══╝  ██║     ██╔═██╗     ╚██╗ ██╔╝████╔╝██║   ████╔╝██║   ╚════██║
███████╗██║  ██║██║     ██║  ██║███████╗   ██║       ██████╔╝███████╗╚██████╗██║  ██╗     ╚████╔╝ ╚██████╔╝██╗╚██████╔╝██╗███████║
╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚══════╝   ╚═╝       ╚═════╝ ╚══════╝ ╚═════╝╚═╝  ╚═╝      ╚═══╝   ╚═════╝ ╚═╝ ╚═════╝ ╚═╝╚══════╝
                                                                                                                                                                                                                                                                                                                                                                               
                                                                                                                                                                  
                                                                                                                                                                  
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

# Инициализация и заполнение keyring для pacman
echo "Инициализация keyring для pacman..."
sudo pacman-key --init || { echo "Ошибка: Не удалось инициализировать keyring."; exit 1; }
sudo pacman-key --populate || { echo "Ошибка: Не удалось заполнить keyring."; exit 1; }
sudo pacman -Syu --noconfirm || { echo "Ошибка: Не удалось обновить систему."; exit 1; }

# Установка TEMP_DIR как текущей директории
TEMP_DIR="$(pwd)"

# Проверка наличия необходимых файлов
required_files=("main_script.sh" "stop_and_clean_nft.sh" "dns.sh" "zapret_gui.py" "zapret-latest" "nfqws" "zapretdeck.desktop" "version.txt" "zapretdeck.png" "requirements.txt")
for file in "${required_files[@]}"; do
    if [ ! -e "$TEMP_DIR/$file" ]; then
        echo "Ошибка: Файл или директория '$file' не найдены в текущей директории"
        exit 1
    fi
done

# Проверка системных зависимостей
dependencies=("bash" "sed" "grep" "awk" "nftables" "python3" "python-pip" "networkmanager" "iproute2" "curl" "git" "tk")
for dep in "${dependencies[@]}"; do
    if ! command -v "$dep" &>/dev/null; then
        echo "y" | sudo pacman -S --noconfirm --needed "$dep"
        if [ $? -ne 0 ]; then
            echo "Ошибка: Не удалось установить $dep. Проверьте подключение к интернету или репозитории."
            exit 1
        fi
    fi
done

# Очистка предыдущей установки
sudo rm -rf /opt/zapretdeck
sudo rm -f /usr/local/bin/zapretdeck
sudo rm -f /usr/share/applications/zapretdeck.desktop
sudo systemctl disable --now zapret_discord_youtube >/dev/null 2>&1
sudo rm -f /etc/systemd/system/zapret_discord_youtube.service
sudo systemctl daemon-reload

# Копирование файлов
sudo mkdir -p /opt/zapretdeck || { echo "Ошибка: Не удалось создать /opt/zapretdeck"; exit 1; }
sudo chmod 755 /opt/zapretdeck
sudo cp -r "$TEMP_DIR/"* /opt/zapretdeck/
sudo chmod +x /opt/zapretdeck/{main_script.sh,stop_and_clean_nft.sh,dns.sh,nfqws}
sudo chmod 644 /opt/zapretdeck/zapretdeck.png
sudo chmod 644 /opt/zapretdeck/requirements.txt

# Создание файла конфигурации с правами для записи
sudo bash -c "cat > /opt/zapretdeck/conf.env" << EOF
interface=
auto_update=false
strategy=
dns=
EOF
sudo chmod 666 /opt/zapretdeck/conf.env
sudo chown $(whoami):$(whoami) /opt/zapretdeck/conf.env

# Создание version.txt
sudo bash -c "echo '0.0.5' > /opt/zapretdeck/version.txt"
sudo chmod 644 /opt/zapretdeck/version.txt

# Создание виртуального окружения и установка Python-зависимостей
sudo python3 -m venv /opt/zapretdeck/venv
sudo /opt/zapretdeck/venv/bin/pip install --upgrade pip
sudo /opt/zapretdeck/venv/bin/pip install -r /opt/zapretdeck/requirements.txt
if [ $? -ne 0 ]; then
    echo "Ошибка: Не удалось установить Python-зависимости. Проверьте подключение к интернету или файл requirements.txt."
    exit 1
fi

# Создание сервиса
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

# Создание символической ссылки
sudo bash -c "echo -e '#!/bin/bash\n/opt/zapretdeck/venv/bin/python3 /opt/zapretdeck/zapret_gui.py' > /usr/local/bin/zapretdeck"
sudo chmod +x /usr/local/bin/zapretdeck

# Настройка прав на лог
sudo touch /opt/zapretdeck/debug.log
sudo chmod 666 /opt/zapretdeck/debug.log

# Активация сервиса
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