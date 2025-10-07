<p align="center">
  <img src="https://raw.githubusercontent.com/rosakodu/zapretdeck/master/zapretdeck.png" alt="ZapretDeck" width="200"/>
</p>

# ZapretDeck — Лёгкий обход блокировок для Steam Deck и Linux

ZapretDeck — простое и удобное приложение для обхода сетевых блокировок YouTube, Discord и Decky Loader. Имеет графический интерфейс для управления сетью и DNS.

**Основные возможности**  
Сети: Выберите Wi-Fi или Ethernet  
Стратегии: Используйте готовые настройки для обхода  
Кнопки Пуск/Стоп: Легко включайте или выключайте сессии  
DNS: Включите или выключите свои DNS  
Автозапуск: Настройте запуск при включении устройства и в игровом режиме

**Зависимости**  

Системные: `pacman` `bash` `nftables` `python3` `curl` `git` `networkmanager` 

Python-модули: `customtkinter` `requests` `pillow` `packaging` `beautifulsoup`

<p align="center">
  <img src="https://raw.githubusercontent.com/rosakodu/zapretdeck/master/screanshots/screenshot.png" alt="Скриншот ZapretDeck" width="400"/>
</p>

**ВАЖНО**  
Remote Play и передача файлов не будут работать во время активации скрипта

Установка и запуск:  
```bash
sudo steamos-readonly disable
mkdir ~/zapretdeck
cd ~/zapretdeck
curl -L -o ZapretDeck_v0.0.4.tar.gz https://github.com/rosakodu/zapretdeck/releases/download/v0.0.4/ZapretDeck_v0.0.4.tar.gz
tar --warning=no-unknown-keyword -xzf ZapretDeck_v0.0.4.tar.gz
rm ZapretDeck_v0.0.4.tar.gz
cd zapretdeck
chmod +x install.sh
./install.sh
