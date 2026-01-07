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

• `ProtonDB` на Steam Deck

• `SteamGridDB` на Steam Deck

• `CSS Loader` на Steam Deck

• `Decky Loader` на Steam Deck

• `Are We Anti-Cheat Yet?` на Steam Deck

Установщик предлагает обновить `SteamOS` и починить `Discover`

• Установщик включает модули из `Geekcom Deck Tools` от <a href="https://github.com/Nospire">Nospire</a>

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

• После обновления SteamOS приложение будет удаляться, а сервис будет работать, рекомендую переустановить приложение

#

Перед установкой задайте пароль через терминал:

```bash
passwd
```

Установка через терминал:

```bash
sudo steamos-readonly disable
mkdir -p ~/zapretdeck
cd ~/zapretdeck || exit 1
curl -L -o ZapretDeck_v0.1.6.tar.gz https://github.com/rosakodu/zapretdeck/releases/download/v.0.1.6/ZapretDeck_v0.1.6.tar.gz
tar -xzf ZapretDeck_v0.1.6.tar.gz --strip-components=1
rm ZapretDeck_v0.1.6.tar.gz
chmod +x ~/zapretdeck/install.sh
sudo ~/zapretdeck/install.sh
```

Деинсталляция:

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
rm -f ~/.local/share/applications/zapretdeck.desktop

# 5. Удаляем временную папку загрузки (если она осталась)
rm -rf ~/zapretdeck

# 6. Обновляем список системных служб
sudo systemctl daemon-reload

# 7. Возвращаем защиту записи (только для SteamOS)
sudo steamos-readonly enable
```

#


