# ZapretDeck - Документация проекта

## Обзор проекта

ZapretDeck — это инструмент для обхода сетевых ограничений (DPI) на Linux системах, оптимизированный для Steam Deck. Проект основан на [zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube) от Flowseal и оригинальном проекте [zapret](https://github.com/bol-van/zapret) от bol-van.

**Основное назначение:** Обход блокировок YouTube, Discord и других сервисов через DPI-спуфинг с использованием nfqws и nftables.

**Текущая версия:** 0.2.2

## Основные технологии

- **Python 3** — основной язык разработки
- **PyQt6** — графический интерфейс пользователя
- **nfqws** — утилита для обхода DPI (из проекта zapret)
- **nftables** — управление сетевыми правилами и очередями
- **systemd** — управление фоновым сервисом
- **Cloudflare WARP** — интеграция VPN для дополнительной защиты
- **Python venv** — изоляция зависимостей проекта

## Архитектура проекта

### Структура директорий

```
zapretdeck/
├── main.py                    # Точка входа, CLI интерфейс
├── ui.py                      # PyQt6 GUI
├── config.py                  # Обёртка над ConfigManager
├── updater.py                 # Потоки Qt: проверка обновлений и установка zipball
├── github_release_updates.py  # GitHub Releases API, semver, каналы stable / devel
├── utils.py                   # Утилиты, ConfigManager, стратегии
├── warp.py                    # Интеграция с Cloudflare WARP
├── monitor.py                 # Мониторинг статуса, тестирование сайтов
├── sys_utils.py               # Системные утилиты, проверки venv
├── main_script.sh             # Основной скрипт запуска стратегий
├── stop_and_clean_nft.sh      # Остановка и очистка правил nftables
├── service.sh                 # Управление systemd сервисом
├── install.sh                 # Установщик проекта
├── requirements.txt           # Python зависимости
├── conf.env                   # Конфигурационный файл
├── nfqws                      # Бинарник nfqws
├── custom-strategies/         # Пользовательские стратегии
├── zapret-latest/             # Стратегии из оригинального zapret
└── i18n/                      # Файлы локализации (TS/QM)
```

### Ключевые модули

#### main.py
Точка входа приложения. Предоставляет CLI интерфейс с подкомандами:
- Запуск GUI (по умолчанию)
- Управление стратегиями
- Запуск/остановка сервиса
- Управление WARP
- Проверка статуса
- Тестирование доступности сайтов

#### ui.py
Графический интерфейс на PyQt6 с современным дизайном:
- **Интегрированный экран приветствия**: Использование `QStackedWidget` для бесшовного перехода от информации к управлению.
- **Гибкий размер**: Окно 1280x800, адаптирующееся под окружение (resizable).
- Выбор стратегий обхода.
- Управление фоновым сервисом.
- Интеграция с WARP (с поддержкой локализованных статусов).
- Мониторинг статуса в реальном времени.
- Поддержка локализации (русский/английский).

#### utils.py
Утилиты и менеджер конфигурации:
- `ConfigManager` — управление конфигурацией (стратегии, фильтр игр)
- `load_strategies()` — загрузка доступных стратегий из директорий
- `check_dependencies()` — проверка системных зависимостей
- Управление путями установки

#### warp.py
Полная интеграция с Cloudflare WARP:
- Проверка установки и регистрации
- Запуск/остановка сервиса WARP
- Подключение/отключение WARP
- Автоматическая регистрация с верификацией
- Очистка при выходе

#### monitor.py
Мониторинг и тестирование:
- `StatusChecker` — поток мониторинга nfqws, сервиса, WARP
- `SiteTester` — проверка доступности YouTube, Discord

#### github_release_updates.py
Универсальный модуль проверки обновлений через [GitHub Releases API](https://docs.github.com/en/rest/releases/releases#list-releases):
- `fetch_all_releases` — загрузка всех опубликованных релизов с пагинацией, обработка 403/404/сетевых ошибок и лимитов (логируется `X-RateLimit-Remaining`).
- `release_matches_channel` / фильтрация: канал **stable** — только `prerelease: false`, без маркера `DEVEL` в теге или названии релиза; канал **devel** — только pre-release и с `DEVEL` в `tag_name` или `name`.
- `find_newer_release` — выбор **максимальной** semver среди подходящих релизов, строго новее локальной версии (`packaging.version`).
- `normalize_version_for_semver` — нормализация строк (`ZapretDeck_`, `v`/`v.`, суффикс `DEVEL`); исправляет прежний антипаттерн `lstrip("v.")`, который обрезал произвольные символы из набора `v` и `.`, а не префикс версии.
- `check_for_updates_sync` — удобная обёртка для GUI/скриптов.

#### updater.py
- `UpdateChecker` (QThread) — вызывает `check_for_updates_sync` и при нахождении релиза шлёт сигнал с `tag_name` и `zipball_url`.
- `UpdaterWorker` — скачивание zipball с `raise_for_status()`, распаковка, запуск `install.sh` в терминале; временная директория удаляется в `finally` (раньше возможна была утечка каталогов).

**Подтверждение пользователем:** диалог «обновить?» остаётся в `ui.py` (`on_update_available`), автоматической установки без согласия нет.

**Пример (скрипт или отладка):**

```python
from github_release_updates import check_for_updates_sync

info, err = check_for_updates_sync("0.2.2", "stable")
if err:
    print("Ошибка:", err)
elif info:
    print("Новый релиз:", info.tag_name, info.zipball_url, info.semver_text)
else:
    print("Уже актуально")
```

#### main_script.sh
Основной shell-скрипт для запуска стратегий:
- Парсинг .bat файлов стратегий
- Настройка nftables с очередями NFQUEUE
- Запуск nfqws с параметрами обхода DPI
- Автоподбор рабочей стратегии

## Сборка и запуск

### Установка

```bash
# Запуск установщика
bash install.sh
```

Установщик автоматически:
- Определяет систему (Arch/SteamOS, Debian/Ubuntu, Fedora и др.)
- Устанавливает системные зависимости (nftables, python3, NetworkManager и др.)
- Создаёт Python virtual environment
- Устанавливает Python зависимости
- Компилирует файлы локализации
- Устанавливает Cloudflare WARP (опционально)
- Создаёт ярлык в меню приложений
- Добавляет команду `zapretdeck` в PATH

### Запуск

```bash
# Запуск GUI
zapretdeck

# Или через ярлык в меню приложений
```

### CLI команды

```bash
# Запуск с конфигурированной стратегией (в foreground)
zapretdeck start

# Остановка ZapretDeck
zapretdeck stop

# Проверка статуса
zapretdeck status

# Активация автоподбора стратегии
zapretdeck strategy auto

# Управление фоновым сервисом
zapretdeck service enable
zapretdeck service disable
zapretdeck service status

# Управление WARP
zapretdeck warp on
zapretdeck warp off
zapretdeck warp status

# Полная настройка (автоподбор + сервис + WARP)
zapretdeck full start

# Тестирование доступности сайтов
zapretdeck --test-sites

# Режим отладки
zapretdeck --debug
```

### Управление сервисом

Фоновый сервис `zapretdeck.service` управляется через systemd:

```bash
# Включить автозапуск
systemctl --user enable zapretdeck.service

# Запустить сервис
systemctl --user start zapretdeck.service

# Проверить статус
systemctl --user status zapretdeck.service

# Просмотреть логи
journalctl --user -u zapretdeck.service -f
```

## Правила разработки

### Стиль кодирования

- **Python:** PEP 8
- **Bash:** Google Shell Style Guide
- **Комментарии:** Описывают "почему", а не "что"
- **Логирование:** Использовать модуль `logging`, уровни DEBUG/INFO/WARNING/ERROR

### Структура Python модулей

```python
#!/usr/bin/env python3
"""
Краткое описание модуля.

Подробное описание назначения и функционала.
"""
import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def example_function(param: str) -> bool:
    """Краткое описание функции.

    Args:
        param: Описание параметра

    Returns:
        Описание возвращаемого значения
    """
    pass
```

### Тестирование

Проект включает модуль тестирования доступности сайтов:

```python
from monitor import SiteTester

tester = SiteTester()
results = tester.test_all()
tester.print_results(results)
```

### Локализация

Файлы локализации находятся в директории `i18n/`:
- `zapretdeck_ru.ts` — исходный файл для русского.
- `zapretdeck_en.ts` — исходный файл для английского (исправлен синтаксис XML для корректной компиляции).
- `zapretdeck_ru.qm` — скомпилированный русский.
- `zapretdeck_en.qm` — скомпилированный английский.

**Особенности текстов:**
- Кнопка WARP меняет текст на транслируемый статус (например, "WARP NOT INSTALL" или "WARP не установлен"), когда сервис не найден.

Компиляция переводов:

```bash
# Скрипт компиляции
bash compile_translations.sh

# Или вручную
lrelease-qt6 i18n/zapretdeck_ru.ts
lrelease-qt6 i18n/zapretdeck_en.ts
```

### Добавление новых стратегий

Стратегии хранятся в формате `.bat` в директориях:
- `custom-strategies/` — пользовательские стратегии
- `zapret-latest/` — стратегии из оригинального zapret

Формат .bat файла:

```batch
@echo off
:: Описание стратегии
bin/nfqws --filter-tcp=443 --dpi-desync=fake --dpi-desync-repeats=6
```

### Конфигурационный файл

`conf.env` содержит основные настройки:

```bash
interface=any
strategy=auto_found.bat
gamefilter=false
auto_update=false
```

## Системные зависимости

### Обязательные

- `python3` — интерпретатор Python 3
- `python3-venv` — модуль virtual environment
- `nft` / `nftables` — управление правилами брандмауэра
- `ip` / `iproute2` — управление сетью
- `curl` — HTTP клиент для тестирования
- `bash` — командная оболочка
- `systemctl` — управление systemd
- `nmcli` — управление NetworkManager
- `pgrep`, `pkill` — управление процессами

### Python зависимости (requirements.txt)

```
PyQt6          # Графический интерфейс
packaging      # Управление версиями
requests       # HTTP запросы для тестирования
psutil         # Системная информация
```

### Опциональные

- `cloudflare-warp-bin` — клиент Cloudflare WARP (Arch/SteamOS)
- `qt6-base` / `qttools5-dev-tools` — инструменты для компиляции переводов

## Поддерживаемые системы

- **Arch Linux** и производные (Manjaro, EndeavourOS, Garuda, CachyOS)
- **SteamOS** / **HoloISO** / **ChimeraOS**
- **Ubuntu** / **Debian** и производные (Linux Mint, Pop!_OS, Kali)
- **ALT Linux**
- **Fedora** / **CentOS** / **RHEL** / **AlmaLinux** / **Rocky**
- **Bazzite**
- **openSUSE** / **SLES**

## Диагностика и отладка

### Включение отладки

```bash
# CLI с отладкой
zapretdeck --debug

# GUI с отладкой (логи в консоль)
zapretdeck --debug
```

### Лог-файлы

- `$HOME/zapretdeck/debug.log` — основной лог приложения
- `$HOME/zapretdeck_install.log` — лог установки
- `journalctl --user -u zapretdeck.service` — логи systemd сервиса

### Проверка зависимостей

```python
from utils import check_dependencies

all_present, missing = check_dependencies()
if not all_present:
    print(f"Missing: {', '.join(missing)}")
```

### Тестирование стратегий

```bash
# Автоподбор стратегии
zapretdeck strategy auto

# Или через GUI: выбрать "Автоподбор" и нажать START
```

## Известные проблемы и решения

### Проблема: nfqws не запускается

**Решение:**
1. Проверьте наличие бинарника: `ls -l $HOME/zapretdeck/nfqws`
2. Проверьте права доступа: `chmod +x $HOME/zapretdeck/nfqws`
3. Проверьте логи: `cat $HOME/zapretdeck/debug.log`

### Проблема: WARP не подключается

**Решение:**
1. Убедитесь, что WARP установлен: `pacman -Qs cloudflare-warp`
2. Проверьте статус сервиса: `systemctl status warp-svc`
3. Перезапустите WARP: `sudo systemctl restart warp-svc`
4. Удалите регистрацию и создайте заново через GUI

### Проблема: Стратегия не работает

**Решение:**
1. Попробуйте другую стратегию из списка
2. Используйте автоподбор: `zapretdeck strategy auto`
3. Проверьте, что nfqws запущен: `pgrep -f nfqws`
4. Проверьте правила nftables: `sudo nft list ruleset`

### Проблема: venv не найден

**Решение:**
```bash
# Переустановите проект
cd /path/to/zapretdeck
bash install.sh
```

## Ресурсы

- **Оригинальный zapret:** https://github.com/bol-van/zapret
- **zapret-discord-youtube:** https://github.com/Flowseal/zapret-discord-youtube
- **Документация nfqws:** https://github.com/bol-van/zapret/blob/master/docs/readme.md#nfqws
- **Cloudflare WARP:** https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/

## Лицензия

Проект распространяется на условиях лицензии MIT.

## Контрибьюция

При внесении изменений:
1. Следуйте PEP 8 для Python кода.
2. Добавляйте логирование для отладки.
3. Обновляйте документацию при изменении функционала.
4. Тестируйте на поддерживаемых системах.
5. Обновляйте версии в `main.py` при релизах.
6. **UI Гайд**: Кнопки должны использовать `_BTN_STYLE_BASE` для консистентности (border-radius: 12px). Баннеры должны использовать `border-image` для корректного растягивания.
