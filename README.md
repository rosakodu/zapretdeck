<p align="center">
  <img src="https://raw.githubusercontent.com/rosakodu/zapretdeck/master/zapretdeck.png" alt="ZapretDeck" width="200"/>
</p>

# ZapretDeck

**Лёгкий обход блокировок для Steam Deck и Linux**

---

ZapretDeck — простое и удобное приложение для обхода сетевых блокировок. Имеет графический интерфейс для управления сетью и DNS.

### Основные возможности:
- **Сети:** Выберите Wi-Fi или Ethernet.
- **Стратегии:** Используйте готовые настройки для обхода.
- **Кнопки Пуск/Стоп:** Легко включайте или выключайте сессии.
- **DNS:** Включите или выключите свои DNS.
- **Автозапуск:** Настройте старт при включении устройства и работы обхода в игровом режиме.
- **Логи:** Всё записывается для поиска ошибок.

---

### Зависимости:
- **Системные:** `bash`, `nftables`, `python3`, `curl`, `git`, `networkmanager`.
- **Python-модули:** `customtkinter`, `requests`.

Перед установкой обязательно установите пароль:  
```bash
passwd

<h2 align="center" style="color: #4CAF50;"> Установка</h2> <div align="center">
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

</div> ```
