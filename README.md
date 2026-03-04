<p align="center">
  <img src="https://raw.githubusercontent.com/rosakodu/zapretdeck/master/zapretdeck.png" alt="ZapretDeck" width="200"/>
</p>

# ZapretDeck — Лёгкий обход блокировок для Steam Deck и Linux
ZapretDeck — простое и удобное приложение для обхода сетевых блокировок. 
Имеет графический интерфейс для управления сетью и возможность работы в фоне.

# 

<p align="center">
  <img src="https://raw.githubusercontent.com/rosakodu/zapretdeck/master/zapretcover.png" alt="zapretdeck cover">
</p>


#

• Создан на основе `zapret-discord-youtube-linux` от <a href="https://github.com/Sergeydigl3">Sergeydigl3</a> 

Открывает доступ:

• `Discord` на Steam Deck

• `YouTube` на Steam Deck

• `Telegram` на Steam Deck

• `ProtonDB` на Steam Deck

• `SteamGridDB` на Steam Deck

• `CSS Loader` на Steam Deck

• `Decky Loader` на Steam Deck

• `Are We Anti-Cheat Yet?` на Steam Deck

#

Сетевые игры, которые будут работать с включенным ZapretDeck и WARP: 

• `Dead by Daylight`

• `Party Animals`

• `R.E.P.O.`

• `Rematch`

• `Fallout 76`

• `Arc Riders`

• `Warframe`

И многие другие...

#


**Зависимости**  

• Системные: `bash` `nftables` `python3` `curl` `git` `networkmanager` 

• Python-модули: `requests` `packaging`

#

## 🐧 Поддерживаемые дистрибутивы

| Семейство | Дистрибутивы                                                       |
|----------|---------------------------------------------------------------------|
| Gaming | SteamOS, ChimeraOS, SteamFork, Bazzite                                |
| Arch-based | Arch, Omarchy, Manjaro, EndeavourOS, Garuda, CachyOS              |
| Debian-based | Ubuntu, Debian, Linux Mint, Pop!_OS, Kali, KDE Neon             |
| RHEL-based | Fedora, CentOS, RHEL, AlmaLinux, Rocky                            |
| SUSE | openSUSE, SLES                                                          |

##

**ВАЖНО**  

• Remote Play и передача файлов не будут работать во время активации скрипта

• После обновления SteamOS WARP будет удаляться, а сервис zapretdeck будет работать, рекомендую переустановить приложение или снова установить WARP

#

Перед установкой задайте пароль через терминал:

```bash
passwd
```

Перед установкой обязательно удалите прошлую версию если она есть:

```bash
# 1. Отключаем защиту записи (только для SteamOS)
sudo steamos-readonly disable

# 2. Останавливаем и отключаем службу, чтобы интернет работал напрямую
sudo systemctl disable --now zapretdeck.service 2>/dev/null || true
sudo systemctl disable --now zapret_discord_youtube.service 2>/dev/null || true

# 3. Очищаем сетевые правила nftables (через встроенный скрипт, если он есть)
if [ -f /opt/zapretdeck/stop_and_clean_nft.sh ]; then
    sudo bash /opt/zapretdeck/stop_and_clean_nft.sh
fi

# 4. Удаляем системные файлы, ярлыки и исполняемую команду
sudo rm -rf /opt/zapretdeck
sudo rm -f /etc/systemd/system/zapretdeck.service
sudo rm -f /etc/systemd/system/zapret_discord_youtube.service
sudo rm -f /usr/local/bin/zapretdeck
sudo rm -f /usr/share/applications/zapretdeck.desktop
sudo rm -f ~/.local/share/applications/zapretdeck.desktop
sudo rm -rf ~/zapretdeck

# 5. Удаляем временную папку загрузки (если она осталась)
rm -rf ~/zapretdeck

# 6. Обновляем список системных служб
sudo systemctl daemon-reload

# 7. Возвращаем защиту записи (только для SteamOS)
sudo steamos-readonly enable
```

Установка:

```bash
# Переходим в Downloads
cd ~/Downloads

# Создаём отдельную папку для установщика
mkdir -p zapretdeck
cd zapretdeck

# Отключаем защиту от записи (обязательно для SteamOS)
sudo steamos-readonly disable

# Скачиваем архив
curl -L -o ZapretDeck_v0.2.0.tar.gz https://github.com/rosakodu/zapretdeck/releases/download/v.0.2.0/ZapretDeck_v0.2.0.tar.gz

# Распаковываем архив
tar -xzf ZapretDeck_v0.2.0.tar.gz --strip-components=1

# Удаляем архив
rm ZapretDeck_v0.2.0.tar.gz

# Делаем скрипт исполняемым
chmod +x install.sh

# Запускаем установку
sudo ./install.sh

# Возвращаем защиту записи (рекомендуется)
sudo steamos-readonly enable

# Возвращаемся в Downloads и удаляем папку установщика
cd ..
rm -rf zapretdeck
```

#


