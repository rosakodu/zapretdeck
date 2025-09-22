ZapretDeck — Лёгкий обход блокировок

ZapretDeck — простое приложение для Steam Deck и Linux, чтобы обходить сетевые блокировки. Оно имеет удобный интерфейс для управления сетью и DNS.

Сети: Выберите Wi-Fi или Ethernet
Стратегии: Используйте готовые настройки для обхода.
Кнопки Пуск/Стоп: Легко включайте или выключайте сессии.
DNS: Включите или выключите свои DNS.
Автозапуск: Настройте старт при включении устройства и работы обхода в игровом режиме.
Логи: Всё записывается для поиска ошибок.


Зависимости: bash, nftables, python3, curl, git, networkmanager.
Python-модули: customtkinter, requests.

Перед установкой обязательно установите пароль:

passwd

Установка:

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
