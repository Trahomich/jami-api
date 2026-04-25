import pytest


@pytest.mark.asyncio
async def test_place_call(mock_dbus_client):
    mock_dbus_client.proxy.placeCall.return_value = "call-123"
    call_id = mock_dbus_client.place_call("acc1", "jami://hash1")
    assert call_id == "call-123"


@pytest.mark.asyncio
async def test_accept_call(mock_dbus_client):
    mock_dbus_client.accept_call("acc1", "call-123")
    mock_dbus_client.proxy.accept.assert_called_once_with("acc1", "call-123")


@pytest.mark.asyncio
async def test_hangup_call(mock_dbus_client):
    mock_dbus_client.hang_up("acc1", "call-123")
    mock_dbus_client.proxy.hangUp.assert_called_once_with("acc1", "call-123")


@pytest.mark.asyncio
async def test_get_call_list(mock_dbus_client):
    mock_dbus_client.proxy.getCallList.return_value = [
        {"id": "call-123", "state": "CURRENT"},
    ]
    calls = mock_dbus_client.get_call_list("acc1")
    assert len(calls) == 1
