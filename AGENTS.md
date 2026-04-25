# Jami Docker Client + API — План разработки

## Архитектура

```
┌─────────────────────────────────────────────┐
│  Docker Container                           │
│                                             │
│  ┌──────────────┐  D-Bus  ┌──────────────┐ │
│  │  REST API    │◄────────►│  jami-daemon  │ │
│  │  (FastAPI)   │          │  (libjami)    │ │
│  │  :8080       │          │              │ │
│  └──────┬───────┘          └──────────────┘ │
│         │                                   │
└─────────┼───────────────────────────────────┘
          │
     HTTP / JSON
          │
    ┌─────▼─────┐
    │  Клиенты   │
    └───────────┘
```

## Этапы разработки

### Этап 1 — Базовая инфраструктура
- Dockerfile на базе debian:bookworm
- Сборка/установка jami-daemon (libjami) из официальных пакетов Jami
- Установка D-Bus session bus
- Python 3.12 + FastAPI + uvicorn
- Библиотека dasbus для D-Bus коммуникации
- docker-compose.yml для запуска контейнера
- entrypoint.sh — запуск D-Bus + jami-daemon + API-сервер

### Этап 2 — API: Управление аккаунтами
- POST /accounts — создать аккаунт Jami
- GET /accounts — список аккаунтов
- GET /accounts/{id} — информация об аккаунте
- DELETE /accounts/{id} — удалить аккаунт
- POST /accounts/{id}/register — привязать к Jami ID (username)

### Этап 3 — API: Контакты
- GET /accounts/{id}/contacts — список контактов
- POST /accounts/{id}/contacts — добавить контакт
- DELETE /accounts/{id}/contacts/{hash} — удалить контакт
- GET /accounts/{id}/contacts/{hash} — детали контакта

### Этап 4 — API: Обмен сообщениями
- POST /accounts/{id}/messages — отправить текстовое сообщение
- GET /accounts/{id}/conversations — список разговоров (swarm)
- GET /accounts/{id}/conversations/{convId}/messages — история сообщений
- WebSocket /ws/accounts/{id}/events — real-time получение сообщений и событий

### Этап 5 — API: Звонки (аудио/видео)
- POST /accounts/{id}/calls — инициировать звонок
- POST /accounts/{id}/calls/{callId}/accept — принять звонок
- POST /accounts/{id}/calls/{callId}/hangup — завершить звонок
- GET /accounts/{id}/calls — активные звонки
- WebSocket-события для входящих звонков

### Этап 6 — API: Файловый обмен
- POST /accounts/{id}/files/send — отправить файл
- GET /accounts/{id}/files/{fileId}/download — скачать файл
- GET /accounts/{id}/files/{fileId}/status — статус передачи

### Этап 7 — Надёжность и продакшен
- Конфигурация через env-переменные и config.yaml
- Healthcheck в Docker (GET /health)
- Volumes для персистентности данных (~/.local/share/jami/)
- Логирование (structlog)
- Аутентификация API (API-key / JWT)
- Тесты (pytest + mocked D-Bus)
- CI/CD (GitHub Actions: lint -> test -> build -> push image)

## Стек технологий

| Компонент | Выбор | Обоснование |
|-----------|-------|-------------|
| Daemon | jami-daemon (deb-пакет) | Официальный, стабильный |
| IPC | D-Bus (session bus) | Стандартный интерфейс jami-daemon |
| API | FastAPI (Python 3.12) | Async, автодокументация, WebSocket |
| D-Bus binding | dasbus | Современный, Python 3, типизированный |
| База | Файловая система Jami | Daemon сам хранит данные |
| Runtime | Docker + docker-compose | Изоляция, воспроизводимость |

## Структура проекта

```
jami-api/
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, startup/shutdown
│   ├── config.py            # Settings from env
│   ├── dbus_client.py       # D-Bus connection to jami-daemon
│   ├── routers/
│   │   ├── accounts.py
│   │   ├── contacts.py
│   │   ├── messages.py
│   │   ├── calls.py
│   │   └── files.py
│   ├── schemas/
│   │   ├── account.py
│   │   ├── contact.py
│   │   ├── message.py
│   │   ├── call.py
│   │   └── file.py
│   ├── services/
│   │   ├── jami_service.py  # Business logic wrapper
│   │   └── event_bus.py     # WebSocket event dispatching
│   └── websocket/
│       └── handler.py       # WS connection manager
├── tests/
│   ├── conftest.py
│   ├── test_accounts.py
│   ├── test_messages.py
│   └── ...
└── .github/
    └── workflows/
        └── ci.yml
```

## Ключевые риски и решения

| Риск | Решение |
|------|---------|
| jami-daemon нет в стандартных репо Debian | Использовать официальный Jami APT-репозиторий или собирать из исходников |
| D-Bus session bus в Docker | Запускать dbus-daemon --session в entrypoint |
| Нет headed-дисплея для daemon | Jami daemon работает headless, не требует GUI |
| Нестабильность D-Bus подключения | Reconnect-логика + healthcheck |
| Concurrent access к D-Bus | Async queue + thread-safe wrapper |

## Команды для проверки

- Lint: `ruff check .`
- Typecheck: `mypy app/`
- Tests: `pytest tests/`
- Build: `docker-compose build`
- Run: `docker-compose up`
