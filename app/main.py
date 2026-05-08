import contextlib

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.dbus_client import JamiDBusClient
from app.routers import accounts, alerts, calls, contacts, files, messages
import app.routers.messages as messages_mod
from app.services.event_bus import EventBus

settings = Settings()
logger = structlog.get_logger()

event_bus = EventBus()
dbus_client = JamiDBusClient.get_instance()

from app.mcp_server import mcp, mcp_app  # noqa: E402


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting_jami_api", host=settings.host, port=settings.port)
    dbus_client.connect(event_bus=event_bus)
    messages_mod.set_event_bus(event_bus)
    async with mcp.session_manager.run():
        logger.info("jami_api_ready")
        yield
    logger.info("shutting_down")
    dbus_client.disconnect()


app = FastAPI(
    title="Jami API",
    description="REST API for Jami messaging daemon",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router, prefix="/api", tags=["accounts"])
app.include_router(contacts.router, prefix="/api", tags=["contacts"])
app.include_router(messages.router, prefix="/api", tags=["messages"])
app.include_router(calls.router, prefix="/api", tags=["calls"])
app.include_router(files.router, prefix="/api", tags=["files"])
app.include_router(alerts.router, prefix="/api", tags=["alerts"])


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok" if dbus_client.is_connected else "degraded",
        "dbus": "connected" if dbus_client.is_connected else "disconnected",
    }


app.mount("/", mcp_app)
