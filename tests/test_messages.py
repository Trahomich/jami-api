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
async def test_get_conversation_messages(mock_dbus_client):
    mock_dbus_client.proxy.getConversationMessages.return_value = [
        {"id": "msg1", "body": "Hi"},
    ]
    messages = mock_dbus_client.get_conversation_messages("acc1", "conv1", 50)
    assert len(messages) == 1
    assert messages[0]["body"] == "Hi"
