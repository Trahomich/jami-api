import pytest


@pytest.mark.asyncio
async def test_send_message(mock_dbus_client):
    mock_dbus_client.proxy.sendTextMessage.return_value = "msg-123"
    msg_id = mock_dbus_client.send_text_message("acc1", "jami://hash1", {"text/plain": "Hello"})
    assert msg_id == "msg-123"


@pytest.mark.asyncio
async def test_get_conversations(mock_dbus_client):
    mock_dbus_client.proxy.getConversations.return_value = ["conv1", "conv2"]
    convs = mock_dbus_client.get_conversations("acc1")
    assert convs == ["conv1", "conv2"]


@pytest.mark.asyncio
async def test_send_conversation_message(mock_dbus_client):
    mock_dbus_client.send_conversation_message("acc1", "conv1", "Hello")
    mock_dbus_client.proxy.sendMessage.assert_called_once_with("acc1", "conv1", "Hello", "", 0)


@pytest.mark.asyncio
async def test_load_conversation(mock_dbus_client):
    mock_dbus_client.proxy.loadConversation.return_value = 1
    result = mock_dbus_client.load_conversation("acc1", "conv1", "", 50)
    assert result == 1
