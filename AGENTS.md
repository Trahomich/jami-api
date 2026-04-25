# AGENTS.md — Jami API

REST API for Jami messaging daemon running in Docker. FastAPI talks to jami-daemon over D-Bus session bus.

## Build / Run Commands

```bash
# Build and run (full stack: dbus + jami-daemon + API)
docker-compose build
docker-compose up

# Inside container or with venv activated:
pip install -e ".[dev]"

# Lint
ruff check .
ruff check --fix .        # auto-fix

# Typecheck (note: gi/dasbus are C bindings, stubs may not exist)
mypy app/

# Tests — all
pytest tests/

# Tests — single file
pytest tests/test_accounts.py

# Tests — single test function
pytest tests/test_accounts.py::test_create_account

# Tests — with verbose output
pytest tests/test_messages.py -v
```

## Architecture

```
Docker Container
├── dbus-daemon (session bus)
├── jami-daemon (/usr/libexec/jamid) — exposes cx.ring.Ring.ConfigurationManager + CallManager on D-Bus
└── FastAPI (:8080)
    ├── /api/*         REST endpoints
    ├── /ws/*          WebSocket events
    └── /mcp           MCP server (Streamable HTTP transport)
```

Key flow: Router → JamiDBusClient (singleton) → D-Bus proxy → jami-daemon.
Events flow in reverse: D-Bus signal → Gio subscription → EventBus → WebSocket.
MCP tools call JamiDBusClient directly, same as REST routers.

## Project Structure

```
app/
├── main.py              # FastAPI app, startup/shutdown lifecycle, /health, mounts MCP
├── config.py            # pydantic-settings (env prefix: JAMI_API_)
├── dbus_client.py       # Singleton D-Bus client, all daemon methods, signal handling
├── mcp_server.py        # MCP server (FastMCP, Streamable HTTP), 15 tools + 3 resources
├── routers/             # FastAPI routers (one per domain)
│   ├── accounts.py      # CRUD /accounts
│   ├── contacts.py      # /accounts/{id}/contacts
│   ├── messages.py      # messaging + WebSocket endpoint
│   ├── calls.py         # /accounts/{id}/calls
│   └── files.py         # file transfer
├── schemas/             # Pydantic request/response models
├── services/
│   ├── jami_service.py  # Thin business logic wrapper around dbus_client
│   └── event_bus.py     # Thread-safe pub/sub (D-Bus → asyncio bridge)
└── websocket/
    └── handler.py       # WebSocket connection manager

tests/
├── conftest.py          # Mocks dasbus/gi modules, provides fixtures
├── test_accounts.py     # Tests via JamiService
├── test_contacts.py     # Tests via JamiDBusClient directly
├── test_messages.py     # Tests via JamiDBusClient directly
├── test_calls.py
├── test_files.py
├── test_event_bus.py
└── test_api_integration.py  # HTTP tests against running service
```

## Code Style

### Formatting & Linting

- **Ruff** with `target-version = "py312"`, `line-length = 100`
- Enabled rules: `E` (pycodestyle), `F` (pyflakes), `I` (isort), `W` (pycodestyle warnings)
- Run `ruff check .` before committing

### Imports

- stdlib → third-party → local (`app.*`), separated by blank lines (enforced by isort/I rule)
- Use `from X import Y` style for specific names
- Never use wildcard imports

### Types

- Use modern Python 3.10+ syntax: `dict[str, str]`, `list[str]`, `X | None` (not `Optional`)
- All functions have return type annotations
- `Any` is used sparingly, mainly for D-Bus proxy and gi types that lack stubs

### Naming Conventions

- Files: `snake_case.py`
- Classes: `PascalCase` (e.g., `JamiDBusClient`, `AccountCreate`, `ConnectionManager`)
- Functions/methods: `snake_case` (e.g., `send_text_message`, `get_account_list`)
- Constants: module-level `SNAKE_CASE` (rare in this codebase)
- Private attributes: `_prefix` (e.g., `_bus`, `_proxy`, `_connected`)
- Pydantic models: noun phrases (`AccountCreate`, `MessageSend`, `CallInfo`)

### Error Handling

- Router errors: catch exceptions → raise `HTTPException(status_code=..., detail=str(e))`
- 404 for get/list operations, 500 for mutations that fail
- D-Bus client: `RuntimeError("D-Bus not connected")` if proxy used while disconnected
- Logging via structlog: `logger.info("event_name", key=value)` style

### Concurrency

- `JamiDBusClient` is a thread-safe singleton (double-checked locking)
- D-Bus event loop runs in a daemon thread (`_event_thread`)
- `EventBus.publish_sync()` uses `threading.Lock` for safe cross-thread publishing
- `EventBus.subscribe()` returns `asyncio.Queue` consumed by WebSocket handlers

### Pydantic Schemas

- One file per domain in `app/schemas/`
- Models extend `BaseModel`
- Default values for optional fields (e.g., `alias: str = ""`)
- No `Config` class — use `model_config` dict when needed

### Routers

- One file per domain in `app/routers/`
- Module-level `router = APIRouter()`
- Registered in `main.py` with `app.include_router(router, prefix="/api", tags=[...])`
- All endpoints are `async def` even when calling synchronous D-Bus methods
- Return type annotations on all endpoints

### Tests

- `conftest.py` mocks `dasbus` and `gi` modules at import level via `sys.modules`
- Two fixtures: `mock_dbus_client` (raw client with `_proxy = MagicMock`) and `mock_service` (JamiService wrapper)
- Tests use `@pytest.mark.asyncio` on every test function
- Test naming: `test_<verb>_<noun>` (e.g., `test_create_account`, `test_send_message`)
- Tests call dbus_client methods directly or via JamiService, then assert on mock calls
- `pytest.ini_options`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`

## Key D-Bus Signatures (discovered during development)

| Method | Signature | Notes |
|--------|-----------|-------|
| `sendTextMessage` | `ssa{ss}i` | `(account, uri, {mime: body}, flag)` |
| `sendMessage` (swarm) | `ssssi` | `(account, conv_id, text, parent_id, flag)` |
| `sendFile` | `sssss` | `(account, conv_id, path, display_name, reply_to)`, void return |
| `loadConversation` | `sssi` | Triggers async `swarmLoaded` + `messagesFound` signals |
| `getLastMessages` | `st` | `(account, base_timestamp_uint64)` |
| Signal `swarmMessageReceived` | tuple | `(account, conv, (msg_id, type, parent, {details}, ...))` |

## Docker Notes

- Base image: `debian:bookworm-slim`
- jami-daemon installed from official Jami nightly APT repo
- Python venv uses `--system-site-packages` for `gi` (PyGObject from system packages)
- Venv at `/opt/venv`, activated via `PATH`
- Entrypoint: `dbus-launch` → `/usr/libexec/jamid` (background) → `uvicorn`
- Volume: `/root/.local/share/jami` for data persistence
- Environment variables: `JAMI_API_HOST`, `JAMI_API_PORT`, `JAMI_API_LOG_LEVEL`
