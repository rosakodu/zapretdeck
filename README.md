<p align="center">
  <img src="https://raw.githubusercontent.com/rosakodu/zapretdeck/master/zapretdeck.png" alt="ZapretDeck" width="200"/>
</p>

# ZapretDeck — Удобный обход блокировок для Steam Deck и Linux

ZapretDeck — простое и удобное приложение для обхода сетевых блокировок YouTube, Discord и Decky Loader. Имеет графический интерфейс для управления сетью и DNS.

**Основные возможности**  

• Используйте готовые настройки для обхода  

• Можно активировать DNS-XBOX.RU

• Работа в фоновом режиме при включении устройства и в игровом режиме

**Зависимости**  

Системные: `bash` `nftables` `python3` `curl` `git` `networkmanager`

Python-модули: `requests` `packaging`

**ВАЖНО**  
Remote Play и передача файлов не будут работать во время работы скрипта.

## 🧠 Поддерживаемые дистрибутивы

> Установщик автоматически определяет вашу систему и обновляет её если это SteamOS. Спасибо решению от https://github.com/Nospire

| 🏷️ Семейство | 🐧 Поддерживаемые дистрибутивы | ⚙️ Менеджер пакетов |
|:-------------|:-------------------------------|:--------------------|
| 🟦 **Arch / SteamOS** | • SteamOS • ChimeraOS • Arch Linux • Manjaro  <br>• EndeavourOS • Garuda • CachyOS | `pacman` |
| 🟩 **Debian / Ubuntu** | • Ubuntu • Debian • Linux Mint • Pop!_OS • Kali Linux | `apt` |
| 🟧 **Fedora / RHEL** | • Fedora • CentOS • RHEL • AlmaLinux • Rocky Linux | `dnf` |
| 🟨 **openSUSE / SLES** | • openSUSE Leap • openSUSE Tumbleweed • SLES | `zypper` |


Перед установкой создайте sudo пароль:
```bash
passwd
```

Установка версии 0.1.3:  
```bash
sudo steamos-readonly disable
mkdir -p ~/zapretdeck
cd ~/zapretdeck || exit 1
curl -L -o ZapretDeck_v0.1.3.tar.gz https://github.com/rosakodu/zapretdeck/releases/download/v.0.1.3/ZapretDeck_v0.1.3.tar.gz
tar -xzf ZapretDeck_v0.1.3.tar.gz --strip-components=1
rm ZapretDeck_v0.1.3.tar.gz
chmod +x ~/zapretdeck/install.sh
sudo ~/zapretdeck/install.sh
```

