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

Установка через терминал:

```bash
# Отключаем защиту от записи (обязательно для SteamOS)
sudo steamos-readonly disable

# Переходим в Downloads (или любую другую удобную папку)
cd ~/Downloads || exit 1

# Создаём отдельную папку, чтобы не мусорить
mkdir -p zapretdeck
cd zapretdeck || exit 1

# Скачиваем самую свежую версию (v.0.2.0)
curl -L -o ZapretDeck_v0.2.0.tar.gz \
     https://github.com/rosakodu/zapretdeck/releases/download/v.0.2.0/ZapretDeck_v0.2.0.tar.gz

# Распаковываем, убирая верхний уровень директории (если он есть)
tar -xzf ZapretDeck_v0.2.0.tar.gz --strip-components=1

# Удаляем архив — место на SSD не бесконечное
rm ZapretDeck_v0.2.0.tar.gz

# Делаем установщик исполняемым
chmod +x install.sh

# Запускаем установку
sudo ./install.sh

# Включаем защиту записи обратно (очень рекомендуется)
sudo steamos-readonly enable

# Опционально: убираем временную папку после установки
# cd .. && rm -rf zapretdeck
```

Деинсталляция:

```bash
# Отключаем защиту файловой системы (SteamOS)
sudo steamos-readonly disable

# Переходим в папку с ZapretDeck
cd ~/Downloads/zapretdeck || exit 1

# Останавливаем сервисы Zapret (если запущены)
sudo systemctl stop zapret zapret.service 2>/dev/null
sudo systemctl disable zapret zapret.service 2>/dev/null

# Удаляем systemd-сервисы
sudo rm -f /etc/systemd/system/zapret.service
sudo systemctl daemon-reload

# Удаляем установленные файлы ZapretDeck
sudo rm -rf /opt/zapretdeck
sudo rm -rf /usr/local/bin/zapret*
sudo rm -rf /etc/zapret
sudo rm -rf ~/zapretdeck

# Удаляем правила iptables/nftables (если применялись)
sudo iptables -F 2>/dev/null
sudo nft flush ruleset 2>/dev/null

# Удаляем папку установки из Downloads
cd ~
rm -rf ~/Downloads/zapretdeck

# Возвращаем защиту записи (SteamOS)
sudo steamos-readonly enable

```

#


