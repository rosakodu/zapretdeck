<p align="center">
  <img src="https://raw.githubusercontent.com/rosakodu/zapretdeck/master/zapretdeck.png" alt="ZapretDeck" width="200"/>
</p>

# ZapretDeck — Простой обход блокировок для Steam Deck и Linux

ZapretDeck — простое и удобное приложение для обхода сетевых блокировок YouTube Discord. Имеет графический интерфейс для управления сетью и DNS.

**Основные возможности:**  

Сети: Выберите Wi-Fi или Ethernet  

Стратегии: Используйте готовые настройки для обхода блокировок YouTube, Discord, Destiny 2

DNS: Используйте DNS от xbox-dns.ru

Автозапуск: Настройте запуск при включении устройства и работы обхода в игровом режиме  


**Зависимости:**  
Системные: `bash`, `nftables`, `python3`, `curl`, `git`, `networkmanager`  
Python-модули: `customtkinter`, `requests`  

**Установка:**  
```bash

sudo steamos-readonly disable
mkdir ~/zapretdeck
cd ~/zapretdeck
wget https://github.com/rosakodu/zapretdeck/releases/download/v0.0.1/ZapretDeck_v0.0.1.tar.gz
tar -xzf ZapretDeck_v0.0.1.tar.gz
rm ZapretDeck_v0.0.1.tar.gz
cd ~/zapretdeck/zapretdeck
chmod +x install.sh
./install.sh
sudo steamos-readonly enable
zapretdeck
