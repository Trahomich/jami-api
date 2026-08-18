import pytest


@pytest.mark.asyncio
async def test_create_account(mock_service):
    mock_service.dbus.proxy.addAccount.return_value = "test-account-id"
    account_id = mock_service.create_account(alias="Test")
    assert account_id == "test-account-id"
    mock_service.dbus.proxy.addAccount.assert_called_once()


@pytest.mark.asyncio
async def test_list_accounts(mock_service):
    mock_service.dbus.proxy.getAccountList.return_value = ["acc1", "acc2"]
    accounts = mock_service.list_accounts()
    assert accounts == ["acc1", "acc2"]


@pytest.mark.asyncio
async def test_delete_account(mock_service):
    mock_service.delete_account("acc1")
    mock_service.dbus.proxy.removeAccount.assert_called_once_with("acc1")


@pytest.mark.asyncio
async def test_get_account_info(mock_service):
    mock_service.dbus.proxy.getAccountDetails.return_value = {
        "Account.type": "RING",
        "Account.alias": "Test",
    }
    mock_service.dbus.proxy.getVolatileAccountDetails.return_value = {
        "Account.registrationStatus": "REGISTERED",
    }
    info = mock_service.get_account_info("acc1")
    assert info["id"] == "acc1"
    assert info["details"]["Account.alias"] == "Test"


@pytest.mark.asyncio
async def test_register_name(mock_service):
    mock_service.dbus.proxy.registerName.return_value = 0
    result = mock_service.register_name("acc1", "myname")
    assert result == 0
