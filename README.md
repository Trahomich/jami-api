# Jami Docker Client + REST API

REST API для управления Jami-демоном в Docker-контейнере через D-Bus. Включает MCP сервер для AI-агентов.

## Запуск

```bash
docker-compose up -d --build
```

API доступен на `http://localhost:8080`, Swagger UI — `http://localhost:8080/docs`.

## Создание аккаунта

```bash
curl -X POST http://localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -d '{"alias":"MyBot"}'
# → {"id":"6b658ed9429e6b8d"}
```

## Отправка приглашения (добавление контакта)

```bash
curl -X POST http://localhost:8080/api/accounts/{account_id}/contacts \
  -H 'Content-Type: application/json' \
  -d '{"uri":"141b732d5c8e82f5e5ba36a9d1f023c866f0af34"}'
# → {"status":"added"}
```

После этого контакт получит запрос на добавление. Когда примет — можно обмениваться сообщениями.

## Получение сообщений (WebSocket)

Подключись к WebSocket для real-time событий (входящие сообщения, звонки, статусы):

```bash
websocat ws://localhost:8080/api/ws/accounts/{account_id}/events
```

Пример входящего сообщения:

```json
{
  "type": "message",
  "source": "swarm",
  "account_id": "6b658ed9429e6b8d",
  "conversation_id": "28ae52ed5d4334a7f3cd8e0b588229d7523e9bd0",
  "message": {
    "id": "949b05c4...",
    "author": "141b732d...",
    "body": "Привет!",
    "timestamp": "1777105547",
    "type": "text/plain"
  }
}
```

## Отправка сообщения

### Через контакт (direct)

```bash
curl -X POST http://localhost:8080/api/accounts/{account_id}/messages \
  -H 'Content-Type: application/json' \
  -d '{"to":"141b732d5c8e82f5e5ba36a9d1f023c866f0af34","body":"Привет!"}'
# → {"message_id":"481613349902297"}
```

### Через swarm-разговор

```bash
curl -X POST http://localhost:8080/api/accounts/{account_id}/conversations/{conv_id}/messages \
  -H 'Content-Type: application/json' \
  -d '{"to":"","body":"Привет из swarm!"}'
# → {"status":"sent"}
```

## Приглашения в беседы

Посмотреть входящие приглашения:

```bash
curl http://localhost:8080/api/accounts/{account_id}/conversation-requests
# → ["7a1e768113e5d04a097836aabcac78c663a58094"]
```

Принять:

```bash
curl -X POST http://localhost:8080/api/accounts/{account_id}/conversation-requests/{conv_id}/accept
# → {"status":"accepted"}
```

Отклонить:

```bash
curl -X POST http://localhost:8080/api/accounts/{account_id}/conversation-requests/{conv_id}/decline
# → {"status":"declined"}
```

## Отправка файла

```bash
curl -X POST http://localhost:8080/api/accounts/{account_id}/files/send \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"28ae52ed5d4334a7f3cd8e0b588229d7523e9bd0","file_path":"/tmp/document.pdf"}'
# → {"interaction_id":"..."}
```

## Скачивание файла

```bash
curl -X POST http://localhost:8080/api/accounts/{account_id}/files/download \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"28ae52ed...","interaction_id":"abc123","file_path":"/tmp/download.pdf"}'
# → {"status":"downloading"}
```

## Статус передачи файла

```bash
curl http://localhost:8080/api/accounts/{account_id}/files/{conversation_id}/{interaction_id}/status
# → {"error_code":0,"path":"/tmp/file","total_size":1024,"bytes_progress":1024}
```

## Prometheus AlertManager

API принимает webhook от Prometheus AlertManager и пересылает алерты в Jami-чат.

### Конфигурация

Задайте переменные окружения (опционально — можно передавать в теле запроса):

```yaml
environment:
  - JAMI_API_ALERT_ACCOUNT_ID=6b658ed9429e6b8d
  - JAMI_API_ALERT_RECIPIENTS=["141b732d5c8e82f5e5ba36a9d1f023c866f0af34"]
```

### AlertManager config

```yaml
receivers:
  - name: 'jami'
    webhook_configs:
      - url: 'http://jami-api:8080/api/alerts'
        send_resolved: true
route:
  receiver: 'jami'
```

### Отправка в swarm-разговор

```bash
curl -X POST http://localhost:8080/api/alerts \
  -H 'Content-Type: application/json' \
  -d '{
    "account_id": "6b658ed9429e6b8d",
    "conversation_id": "28ae52ed5d4334a7f3cd8e0b588229d7523e9bd0",
    "webhook": {
      "receiver": "jami",
      "status": "firing",
      "alerts": [{
        "status": "firing",
        "labels": {"alertname": "HighCpu", "severity": "critical"},
        "annotations": {"summary": "CPU > 90%"},
        "starts_at": "2026-01-01T00:00:00Z"
      }],
      "external_url": "http://alertmanager:9093"
    }
  }'
# → {"status":"ok","sent":1,"failed":0,"details":[{"conversation_id":"28ae52ed...","status":"sent"}]}
```

### Отправка напрямую контактам

```bash
curl -X POST http://localhost:8080/api/alerts \
  -H 'Content-Type: application/json' \
  -d '{
    "account_id": "6b658ed9429e6b8d",
    "recipients": ["141b732d5c8e82f5e5ba36a9d1f023c866f0af34"],
    "webhook": {
      "status": "firing",
      "alerts": [{"status": "firing", "labels": {"alertname": "DiskFull"}, "annotations": {"summary": "Disk > 95%"}}]
    }
  }'
```

## MCP Server

API включает MCP сервер (Streamable HTTP transport) на `POST /mcp` для интеграции с AI-агентами (Claude, Cursor, и т.д.).

### Конфигурация клиента

Добавьте в MCP клиент (например, Claude Desktop, Cursor):

```json
{
  "mcpServers": {
    "jami": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

### Доступные инструменты (15)

| Tool | Описание |
|------|----------|
| `list_accounts` | Список аккаунтов Jami |
| `get_account_info` | Детали аккаунта |
| `get_account_status` | Runtime-статус (registration, DHT) |
| `list_contacts` | Список контактов |
| `add_contact` | Добавить контакт |
| `remove_contact` | Удалить контакт |
| `list_conversations` | Список swarm-разговоров |
| `send_message` | Отправить сообщение в swarm |
| `send_direct_message` | Отправить прямое сообщение |
| `place_call` | Позвонить |
| `hangup_call` | Завершить звонок |
| `accept_call` | Принять звонок |
| `list_calls` | Список активных звонков |
| `send_file` | Отправить файл |
| `get_file_status` | Статус передачи файла |

### Доступные ресурсы (3)

| URI | Описание |
|-----|----------|
| `jami://accounts` | Все аккаунты с деталями |
| `jami://accounts/{id}/contacts` | Контакты аккаунта |
| `jami://accounts/{id}/conversations` | Разговоры аккаунта |

## API Reference

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| POST | `/api/accounts` | Создать аккаунт |
| GET | `/api/accounts` | Список аккаунтов |
| GET | `/api/accounts/{id}` | Информация об аккаунте |
| DELETE | `/api/accounts/{id}` | Удалить аккаунт |
| POST | `/api/accounts/{id}/register` | Зарегистрировать имя |
| GET | `/api/accounts/{id}/contacts` | Список контактов |
| POST | `/api/accounts/{id}/contacts` | Добавить контакт |
| DELETE | `/api/accounts/{id}/contacts/{uri}` | Удалить контакт |
| GET | `/api/accounts/{id}/contacts/{uri}` | Детали контакта |
| POST | `/api/accounts/{id}/messages` | Отправить direct-сообщение |
| POST | `/api/accounts/{id}/conversations/{conv_id}/messages` | Отправить в swarm |
| GET | `/api/accounts/{id}/conversations` | Список разговоров |
| GET | `/api/accounts/{id}/conversations/{conv_id}/messages` | Загрузить историю |
| POST | `/api/accounts/{id}/files/send` | Отправить файл |
| POST | `/api/accounts/{id}/files/download` | Скачать файл |
| GET | `/api/accounts/{id}/files/{conv_id}/{file_id}/status` | Статус файла |
| POST | `/api/accounts/{id}/calls` | Позвонить |
| POST | `/api/accounts/{id}/calls/{call_id}/accept` | Принять звонок |
| POST | `/api/accounts/{id}/calls/{call_id}/hangup` | Завершить звонок |
| GET | `/api/accounts/{id}/calls` | Активные звонки |
| WS | `/api/ws/accounts/{id}/events` | Real-time события |
| POST | `/api/alerts` | AlertManager webhook → Jami |
| POST | `/api/bots` | Создать бота (токен для Bot API) |
| GET | `/api/bots` | Список ботов |
| DELETE | `/api/bots/{token}` | Удалить бота |
| POST/GET | `/bot{token}/{method}` | Telegram Bot API-совместимые методы |
| GET | `/bot{token}/files/{file_id}/{name}` | Скачать файл бота |
| POST | `/mcp` | MCP сервер (Streamable HTTP) |
| GET | `/health` | Healthcheck |

## Telegram Bot API (совместимый слой)

На базе этого API реализован фасад, совместимый с Telegram Bot API: боты, написанные
под Telegram (aiogram, telebot, python-telegram-bot и т.п.), могут работать без
Telegram — достаточно указать этот сервер как base URL.

### Как это работает

| Telegram | Здесь | Примечание |
|----------|-------|------------|
| Bot token (от @BotFather) | Токен из `POST /api/bots` | Привязан к Jami-аккаунту |
| `chat_id` (число) | Swarm-беседа или контакт | Маппинг хранится в SQLite, стабилен |
| `update_id` | Автоинкремент в SQLite | Та же семантика offset-подтверждения |
| Webhook | HTTP POST на ваш URL | Тот же формат + `X-Telegram-Bot-Api-Secret-Token` |
| `message_id` | ID в локальной БД | Для `reply_to_message_id` |
| `file_id` | UUID + interaction Jami | Скачивание через `/bot<token>/files/...` |

Числовые ID детерминированы: приватные чаты положительные, группы отрицательные
(как в Telegram). Собственные сообщения бота не возвращаются апдейтами (как в Telegram).

### Быстрый старт

**Шаг 1. Создай Jami-аккаунт для бота** (если ещё нет):

```bash
curl -X POST http://localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -d '{"alias":"MyBot"}'
# → {"id":"6b658ed9429e6b8d"}
```

**Шаг 2. Выпусти токен бота:**

```bash
curl -X POST http://localhost:8080/api/bots \
  -H 'Content-Type: application/json' \
  -d '{"account_id":"6b658ed9429e6b8d","name":"MyBot"}'
# → {"token":"287868514:f27f4fd2063bcf9872f47dce3b6dc23d","account_id":"...","name":"MyBot"}
```

**Шаг 3. Дай пользователям способ найти бота.** Узнай Jami ID аккаунта бота:

```bash
curl -s http://localhost:8080/api/accounts/6b658ed9429e6b8d \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['details']['Account.username'])"
# → 6ae9a2e2d20131a7b94d9f0cf5ac7c63ed9d9004  (это и есть «username» бота)
```

Пользователь добавляет этот ID в контакты своего Jami и пишет первым сообщением —
чат создастся автоматически при первом входящем. Для групповой беседы — пригласите
аккаунт бота в swarm-беседу.

**Шаг 4. Проверь:**

```bash
curl -X POST http://localhost:8080/bot287868514:f27f4fd.../getMe
# → {"ok":true,"result":{"id":44360095681333431,"is_bot":true,
#     "first_name":"MyBot","username":"jami_6b658ed9429e"}}
```

### Поддерживаемые методы

| Метод | Параметры | Примечание |
|-------|-----------|------------|
| `getMe` | — | Имя = alias аккаунта |
| `sendMessage` | `chat_id`, `text`, `reply_to_message_id` | `parse_mode` игнорируется |
| `getUpdates` | `offset`, `timeout` (long polling, ≤50s), `limit` | Подтверждение через `offset` |
| `setWebhook` | `url`, `secret_token`, `drop_pending_updates` | Webhook и polling взаимоисключаемы по факту доставки |
| `deleteWebhook` | `drop_pending_updates` | |
| `getWebhookInfo` | — | + `pending_update_count`, `last_error_message` |
| `getChat` | `chat_id` | |
| `sendChatAction` | `chat_id`, `action` | Всегда `true` (no-op) |
| `sendDocument` | `chat_id`, `document` (multipart или `file_id`), `caption` | Только swarm-беседы |
| `sendPhoto` | `chat_id`, `photo` (multipart или `file_id`), `caption` | Как document |
| `getFile` | `file_id` | Для входящих — триггерит загрузку |
| `GET /bot{token}/files/{file_id}/{name}` | — | Скачивание файла |

Ответы в формате Telegram: `{"ok":true,"result":...}` /
`{"ok":false,"error_code":400,"description":"Bad Request: ..."}`.
Параметры принимаются как JSON-тело, form-data или query — как у оригинала.

### Long polling

```bash
curl -X POST 'http://localhost:8080/bot<token>/getUpdates?timeout=25'
# → {"ok":true,"result":[{"update_id":1,"message":{
#     "message_id":1,
#     "from":{"id":3988456598134798,"is_bot":false,"first_name":"46bd6008"},
#     "chat":{"id":56414509159708860,"type":"private","first_name":"46bd6008"},
#     "date":1787052354,"text":"Привет, бот!"}}]}
```

Подтверждение обработки — следующий запрос с `offset = последний update_id + 1`
(всё, что ниже offset, удаляется из очереди):

```bash
curl -X POST http://localhost:8080/bot<token>/getUpdates \
  -H 'Content-Type: application/json' -d '{"offset":2,"timeout":25}'
```

### Webhook

```bash
curl -X POST http://localhost:8080/bot<token>/setWebhook \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://bot.example.com/hook","secret_token":"s3cret"}'
```

Сервер будет POST-ить апдейты на URL в формате Telegram с заголовком
`X-Telegram-Bot-Api-Secret-Token: s3cret` (проверяйте его в своём обработчике).
Успешно доставленный апдейт (HTTP 2xx) удаляется из очереди; при ошибке остаётся
доступным через `getUpdates`, а текст последней ошибки виден в `getWebhookInfo`.

### Отправка сообщений и реплаи

```bash
curl -X POST http://localhost:8080/bot<token>/sendMessage \
  -H 'Content-Type: application/json' \
  -d '{"chat_id":-31334997035030108,"text":"Ответ бота","reply_to_message_id":2}'
# → {"ok":true,"result":{"message_id":3,"chat":{"id":-31334997035030108,
#     "type":"group","title":"55ef8b3c"},"date":1787052830,"text":"Ответ бота"}}
```

`reply_to_message_id` транслируется в parent-message swarm — в клиенте Jami это
отображается как ответ на сообщение.

### Файлы

Отправка (multipart, как в Telegram):

```bash
curl -X POST http://localhost:8080/bot<token>/sendDocument \
  -F chat_id=-31334997035030108 -F caption="Отчёт" -F document=@/tmp/report.pdf
# → {"ok":true,"result":{"message_id":4,"document":{
#     "file_id":"7bd0f350be8d442695ac69b34111ccb9","file_name":"report.pdf",
#     "file_size":10240},"caption":"Отчёт"}}
```

Повторная отправка уже загруженного файла — по `file_id` вместо multipart.

Входящие файлы приходят апдейтом с полем `document`. Скачивание двухшаговое, как
в Telegram: `getFile` (для входящих триггерит загрузку из DHT) → GET по `file_path`:

```bash
curl -X POST http://localhost:8080/bot<token>/getFile \
  -H 'Content-Type: application/json' -d '{"file_id":"<file_id>"}'
# → {"ok":true,"result":{"file_id":"...","file_size":18,
#     "file_path":"files/<file_id>/notes.txt"}}

curl -OJ http://localhost:8080/bot<token>/files/<file_id>/notes.txt
```

### Подключение реальных Telegram-библиотек

**aiogram 3.x** — укажите `base_url` при создании Bot:

```python
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

API_BASE = "http://localhost:8080"   # наш сервер вместо api.telegram.org

bot = Bot(token="287868514:f27f4fd2063bcf9872f47dce3b6dc23c", base_url=API_BASE)
dp = Dispatcher()

@dp.message(F.text)
async def echo(message: Message):
    await message.reply(f"Эхо: {message.text}")

async def main():
    await dp.start_polling(bot)   # long polling через getUpdates

import asyncio
asyncio.run(main())
```

**pyTelegramBotAPI (telebot)** — параметр `api_url`:

```python
import telebot

API_BASE = "http://localhost:8080"
bot = telebot.TeleBot(
    "287868514:f27f4fd2063bcf9872f47dce3b6dc23c",
    api_url=API_BASE + "/bot{0}/{1}",
)

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "Привет! Я работаю на Jami.")

bot.infinity_polling()
```

**python-telegram-bot** — `base_url` в Defaults:

```python
from telegram import BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

app = (
    ApplicationBuilder()
    .token("287868514:f27f4fd2063bcf9872f47dce3b6dc23c")
    .base_url("http://localhost:8080/bot")
    .build()
)

async def echo(update, context):
    await update.message.reply_text(f"Эхо: {update.message.text}")

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
app.run_polling()
```

Неиспользуемые фичи (клавиатуры, стикеры, `editMessageText` и т.п.) библиотеки
могут вызывать на старте — например, aiogram вызывает `setMyCommands`/`deleteWebhook`;
неизвестные методы возвращают `404 ... not supported` и обычно не блокируют polling.
Если блокируют — отключите startup-вызовы (`skip_updates=True`, не используйте
`set_my_commands`).

### Управление ботами (админ-API)

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| POST | `/api/bots` | Создать токен: `{"account_id": "...", "name": "..."}` |
| GET | `/api/bots` | Список ботов |
| DELETE | `/api/bots/{token}` | Отозвать токен |

Токены и маппинги хранятся в SQLite (`JAMI_API_DB_PATH`, по умолчанию
`/root/.local/share/jami/botapi.db` — на персистентном volume). Файлы ботов —
`JAMI_API_FILES_DIR`. Один аккаунт может иметь несколько токенов (несколько «ботов»).

### Ограничения и особенности

- Нет inline-клавиатур/callback-кнопок, стикеров, платежей, mini-apps — их нет
  в протоколе Jami; бот, завязанный на них, не перенесётся.
- Отправка файлов — только в swarm-беседы (Jami не делает file transfer в direct).
- `parse_mode` (Markdown/HTML) игнорируется — текст уходит как plain text.
- Не реализованы `editMessageText`/`deleteMessage`/реакции (план: фаза 2).
- Доставка между устройствами идёт через DHT: возможна задержка в секунды/десятки
  секунд — закладывайте таймауты в клиенте.
- `getUpdates` и webhook: доставленный webhook-апдейт исчезает из очереди polling.
- Прямых (direct) сообщений от неподтверждённых контактов демон не принимает —
  пользователь должен добавить аккаунт бота в контакты (двусторонний trust).
- Фигурирующие в коде клиента «usernames» вида `jami_<account_id>` — синтетические,
  реального namespace имён в Jami для них нет (есть только регистрируемые имена
  через `/api/accounts/{id}/register`).
