<p align="center">
  <img src="https://raw.githubusercontent.com/rosakodu/zapretdeck/master/zapretdeck.png" alt="ZapretDeck" width="200"/>
</p>

# ZapretDeck — Лёгкий обход блокировок для Steam Deck и Linux

ZapretDeck — простое и удобное приложение для обхода сетевых блокировок YouTube, Discord и Decky Loader. Имеет графический интерфейс для управления сетью и DNS.

**Основные возможности**  
Используйте готовые настройки для обхода  
Можно активировать DNS-XBOX.RU
Работа в фоновом режиме при включении устройства и в игровом режиме

**Зависимости**  

Системные: `bash` `nftables` `python3` `curl` `git` `networkmanager`

Python-модули: `requests` `packaging`

**ВАЖНО**  
Remote Play и передача файлов не будут работать во время работы скрипта.

Перед установкой создайте sudo пароль:
```bash
passwd
```

Установка стабильной 0.1.0:  
```bash
sudo steamos-readonly disable
mkdir -p ~/zapretdeck
cd ~/zapretdeck || exit 1
curl -L -o ZapretDeck_v0.1.0.tar.gz https://github.com/rosakodu/zapretdeck/releases/download/v.0.1.0/ZapretDeck_v0.1.0.tar.gz
tar -xzf ZapretDeck_v0.1.0.tar.gz --strip-components=1
rm ZapretDeck_v0.1.0.tar.gz
chmod +x ~/zapretdeck/install.sh
sudo ~/zapretdeck/install.sh
```


