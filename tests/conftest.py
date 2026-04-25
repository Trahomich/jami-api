import sys
from unittest.mock import MagicMock

import pytest

sys.modules["gi"] = MagicMock()
sys.modules["gi.repository"] = MagicMock()
sys.modules["dasbus"] = MagicMock()
sys.modules["dasbus.client"] = MagicMock()
sys.modules["dasbus.client.proxy"] = MagicMock()
sys.modules["dasbus.connection"] = MagicMock()
sys.modules["dasbus.loop"] = MagicMock()
sys.modules["structlog"] = MagicMock()
sys.modules["pydantic_settings"] = MagicMock()
sys.modules["mcp"] = MagicMock()
sys.modules["mcp.server"] = MagicMock()
sys.modules["mcp.server.fastmcp"] = MagicMock()
sys.modules["mcp.server.transport_security"] = MagicMock()


@pytest.fixture
def mock_dbus_client():
    from app.dbus_client import JamiDBusClient

    client = JamiDBusClient.__new__(JamiDBusClient)
    client._bus = MagicMock()
    client._event_loop = MagicMock()
    client._proxy = MagicMock()
    client._call_proxy = MagicMock()
    client._connected = True
    client._event_thread = None
    return client


@pytest.fixture
def mock_service(mock_dbus_client):
    from app.services.jami_service import JamiService

    return JamiService(client=mock_dbus_client)
