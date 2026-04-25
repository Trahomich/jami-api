import sys
from unittest.mock import MagicMock

import pytest

sys.modules["dasbus"] = MagicMock()
sys.modules["dasbus.client"] = MagicMock()
sys.modules["dasbus.client.proxy"] = MagicMock()
sys.modules["dasbus.connection"] = MagicMock()
sys.modules["dasbus.loop"] = MagicMock()


@pytest.fixture
def mock_dbus_client():
    from app.dbus_client import JamiDBusClient

    client = JamiDBusClient.__new__(JamiDBusClient)
    client._bus = MagicMock()
    client._event_loop = MagicMock()
    client._proxy = MagicMock()
    client._connected = True
    client._event_thread = None
    return client


@pytest.fixture
def mock_service(mock_dbus_client):
    from app.services.jami_service import JamiService

    return JamiService(client=mock_dbus_client)
