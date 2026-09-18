# Telegram Channel Bot

Бот для операторов: привязка каналов, публикация постов и ответы на сообщения канала / обсуждений.

**Стек:** Python 3.11+, aiogram 3.x, pydantic-settings, aiosqlite.

> Если токен бота когда-либо попадал в чат, логи или скриншоты — **сразу смените его** в [@BotFather](https://t.me/BotFather) (`/revoke`).

## Возможности

| Команда | Описание |
|---------|----------|
| `/start` | Справка (доступна всем) |
| `/bind` | Привязать канал (переслать пост или указать `@username` / ID) |
| `/channels` | Список привязанных каналов |
| `/post` | Опубликовать текст или медиа в канал |
| `/reply` | Ответить на пост / сообщение (пересылка, ссылка t.me или `chat_id message_id`) |
| `/cancel` | Отменить текущий сценарий |

Команды записи доступны **только** пользователям из `ALLOWED_USER_IDS`. Остальные получают отказ на русском.

## Подготовка в Telegram

1. Создайте бота у [@BotFather](https://t.me/BotFather) → `/newbot` → сохраните токен.
2. Добавьте бота в канал **администратором** с правом **«Публикация сообщений»** (Post messages).
3. Узнайте свой Telegram user ID через [@userinfobot](https://t.me/userinfobot) — он понадобится для allowlist.
4. (Опционально) Для ответов в обсуждениях добавьте бота в группу обсуждений канала.

## Конфигурация (только env)

Скопируйте пример и заполните значения (файл `.env` в git не попадает):

```bash
cp .env.example .env
```

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | да | Токен от BotFather |
| `ALLOWED_USER_IDS` | да* | ID операторов через запятую, например `123456789,987654321` |
| `DEFAULT_CHANNEL_ID` | нет | Канал по умолчанию для `/post` |
| `DB_PATH` | нет | Путь к SQLite (по умолчанию `./data/bot.db`) |

\* Без `ALLOWED_USER_IDS` все write-команды будут отклоняться.

## Локальный запуск (venv)

```bash
cd /workspace/telegram-channel-bot   # или путь к клону
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# для тестов: pip install -r requirements-dev.txt

# заполните .env (токен и ALLOWED_USER_IDS)
python -m bot.main
```

Проверка без сети Telegram:

```bash
python -m compileall bot tests
pytest -q
```

## Docker

```bash
cp .env.example .env
# отредактируйте .env

docker compose up -d --build
docker compose logs -f bot
```

Данные SQLite хранятся в volume `bot-data`.

## Структура проекта

```
bot/
  config.py          # pydantic-settings
  db.py              # aiosqlite
  main.py            # polling entrypoint
  handlers/          # /start /bind /channels /post /reply
  services/          # привязка, публикация, ответы, парсинг
  middlewares/       # allowlist
tests/               # unit-тесты без живого API
Dockerfile
docker-compose.yml
.env.example
```

## Безопасность

- Токен и секреты — **только** в переменных окружения / `.env`, никогда в коде и коммитах.
- Логи структурированные: логируются `user_id`, `channel_id`, `message_id`, **не** токен.
- `.gitignore` исключает `.env`, `*.db`, `.venv`, `__pycache__` и т.п.

## Лицензия

MIT (использование на свой страх и риск).
