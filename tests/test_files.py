import pytest


@pytest.mark.asyncio
async def test_send_file(mock_dbus_client):
    mock_dbus_client.proxy.sendFile.return_value = "interaction-123"
    result = mock_dbus_client.send_file("acc1", "conv1", "/tmp/test.txt")
    assert result == "interaction-123"


@pytest.mark.asyncio
async def test_download_file(mock_dbus_client):
    mock_dbus_client.download_file("acc1", "conv1", "int-1", "/tmp/download.txt")
    mock_dbus_client.proxy.downloadFile.assert_called_once()


@pytest.mark.asyncio
async def test_file_transfer_info(mock_dbus_client):
    mock_dbus_client.proxy.fileTransferInfo.return_value = {
        "status": "completed",
        "totalSize": 1024,
    }
    info = mock_dbus_client.file_transfer_info("acc1", "conv1", "int-1")
    assert info["status"] == "completed"
