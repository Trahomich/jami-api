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
| POST | `/mcp` | MCP сервер (Streamable HTTP) |
| GET | `/health` | Healthcheck |
