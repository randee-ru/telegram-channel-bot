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
| `AGENT_API_TOKEN` | для HTTP API | Bearer-токен локального Agent API |
| `AGENT_API_PORT` | нет | Порт API (по умолчанию `8787`) |
| `AGENT_API_HOST` | нет | Хост API (по умолчанию `127.0.0.1`) |

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
  handlers/          # /start /bind /channels /post /reply + ingest
  agent_api.py       # локальный HTTP API для агентов
  services/          # привязка, публикация, ответы, парсинг
  middlewares/       # allowlist
tools/tgctl.py       # CLI для агентов
tests/               # unit-тесты без живого API
Dockerfile
docker-compose.yml
.env.example
```


## Управление для агентов (Боря / Лилу)

Программный доступ к тому же боту: публикация в личный канал, чтение сохранённых постов, инфо о канале, ответы.

**Ограничение Telegram Bot API:** бот не может прокрутить всю историю канала. В SQLite попадают только посты с момента, когда бот — админ канала и получает обновления `channel_post` / `edited_channel_post` (плюс посты, опубликованные через API/CLI).

### Конфиг

| Переменная | Описание |
|------------|----------|
| `AGENT_API_TOKEN` | Секрет Bearer-токена; без него HTTP API **выключен** |
| `AGENT_API_PORT` | Порт (по умолчанию `8787`) |
| `AGENT_API_HOST` | Хост (по умолчанию `127.0.0.1` — только localhost) |

### HTTP API (локально, вместе с ботом)

Базовый URL: `http://127.0.0.1:8787`

Авторизация (кроме `/health`): заголовок `Authorization: Bearer <AGENT_API_TOKEN>` или `X-Agent-Token: <AGENT_API_TOKEN>`.

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Без auth |
| GET | `/channels` | Список привязанных каналов |
| POST | `/channels/default` | `{"channel_id": -100...}` — канал по умолчанию |
| GET | `/channels/info?channel_id=` | getChat + число участников |
| POST | `/post` | `{"text":"...","channel_id":optional,"parse_mode":optional}` |
| POST | `/reply` | `{"chat_id":...,"message_id":...,"text":"..."}` |
| GET | `/posts?channel_id=&limit=20` | Недавние посты из SQLite |
| GET | `/posts/search?q=&channel_id=&limit=20` | LIKE-поиск по text/caption |
| GET | `/sources` | Watched news sources |
| GET | `/feed?limit=&chat_id=&include_own=` | Лента источников (без своего канала по умолчанию) |

Токен бота в ответах **никогда** не возвращается. Ошибки — JSON `{"ok":false,"error":{"code","message"}}`.

Пример:

```bash
curl -s http://127.0.0.1:8787/health
curl -s -H "Authorization: Bearer $AGENT_API_TOKEN" http://127.0.0.1:8787/channels
curl -s -H "Authorization: Bearer $AGENT_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Привет от агента"}' \
  http://127.0.0.1:8787/post
```

### CLI (`tools/tgctl.py`)

Работает напрямую через aiogram + SQLite (не зависит от HTTP API):

```bash
cd /workspace/telegram-channel-bot
source .venv/bin/activate

python tools/tgctl.py channels
python tools/tgctl.py sources
python tools/tgctl.py feed [--limit 20] [--chat-id ID] [--include-own]
python tools/tgctl.py set-default -1001234567890
python tools/tgctl.py info [--channel ID]
python tools/tgctl.py post --text "hello" [--channel ID]
python tools/tgctl.py posts [--channel ID] [--limit 20]
python tools/tgctl.py search "query" [--channel ID]
python tools/tgctl.py reply --chat-id ID --message-id ID --text "..."
```

Перед публикацией через агентов: привяжите канал (`/bind` в Telegram) и при необходимости `set-default` / `POST /channels/default`. Если личного канала ещё нет в БД — нужен `channel_id` от пользователя.


## Источники новостей (группы / каналы для Lilu / Бори)

Бот `@aishost_bot` можно добавить во многие группы и каналы как **источник новостей**. Сообщения сохраняются в SQLite; агенты читают ленту через CLI / HTTP API.

### Настройка в BotFather и Telegram

1. У [@BotFather](https://t.me/BotFather): `/setprivacy` → выберите бота → **Disable**.  
   Иначе в группах бот видит только команды и упоминания, а не обычные сообщения.
2. Добавьте бота в нужные **каналы** (админом, хотя бы с правом читать сообщения / постить не обязательно для ingest) и/или **группы / супергруппы**.
3. При добавлении бот получает `my_chat_member` и записывает чат в таблицу `watched_chats` (роль `news_source`). При кике / выходе чат помечается `is_active=0`.
4. **История до момента добавления недоступна** Bot API: в БД попадают только сообщения с момента, когда бот уже в чате (и privacy выключен для групп).

Личный канал для публикации (`channels` + `is_default`, например `@randee_create`) остаётся отдельным publish-target; по умолчанию его посты **не** смешиваются с новостной лентой.

### Как Lilu / Боря читают ленту

```bash
# Список источников (тип, title, last_message_at)
python tools/tgctl.py sources

# Недавние посты из источников (без личного канала)
python tools/tgctl.py feed --limit 30

# Один чат или включая свой канал
python tools/tgctl.py feed --chat-id -100... --limit 20
python tools/tgctl.py feed --include-own --limit 50
```

HTTP (тот же токен Agent API):

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/sources` | Watched chats (`?role=&active=1`) |
| GET | `/feed?limit=&chat_id=&include_own=` | Лента ingest (по умолчанию без личного канала) |

## Безопасность

- Токен и секреты — **только** в переменных окружения / `.env`, никогда в коде и коммитах.
- Логи структурированные: логируются `user_id`, `channel_id`, `message_id`, **не** токен.
- `.gitignore` исключает `.env`, `*.db`, `.venv`, `__pycache__` и т.п.

## Лицензия

MIT (использование на свой страх и риск).
