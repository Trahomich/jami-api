import pytest


@pytest.mark.asyncio
async def test_list_contacts(mock_dbus_client):
    mock_dbus_client.proxy.getContacts.return_value = [
        {"uri": "jami://hash1", "displayName": "Alice"},
    ]
    contacts = mock_dbus_client.get_contacts("acc1")
    assert len(contacts) == 1
    assert contacts[0]["uri"] == "jami://hash1"


@pytest.mark.asyncio
async def test_add_contact(mock_dbus_client):
    mock_dbus_client.add_contact("acc1", "jami://hash2")
    mock_dbus_client.proxy.addContact.assert_called_once_with("acc1", "jami://hash2")


@pytest.mark.asyncio
async def test_remove_contact(mock_dbus_client):
    mock_dbus_client.remove_contact("acc1", "jami://hash2")
    mock_dbus_client.proxy.removeContact.assert_called_once_with("acc1", "jami://hash2", False)
