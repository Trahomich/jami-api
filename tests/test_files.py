import pytest


@pytest.mark.asyncio
async def test_send_file(mock_dbus_client):
    mock_dbus_client.proxy.sendFile.return_value = "interaction-123"
    result = mock_dbus_client.send_file("acc1", "conv1", "/tmp/test.txt")
    assert result == "interaction-123"
    mock_dbus_client.proxy.sendFile.assert_called_once_with(
        "acc1", "conv1", "/tmp/test.txt", "", ""
    )


@pytest.mark.asyncio
async def test_download_file(mock_dbus_client):
    mock_dbus_client.download_file("acc1", "conv1", "int-1", "/tmp/download.txt")
    mock_dbus_client.proxy.downloadFile.assert_called_once_with(
        "acc1", "conv1", "int-1", "int-1", "/tmp/download.txt"
    )


@pytest.mark.asyncio
async def test_file_transfer_info(mock_dbus_client):
    mock_dbus_client.proxy.fileTransferInfo.return_value = (0, "/tmp/file.txt", 1024, 512)
    info = mock_dbus_client.file_transfer_info("acc1", "conv1", "int-1")
    assert info["error_code"] == 0
    assert info["path"] == "/tmp/file.txt"
    assert info["total_size"] == 1024
    assert info["bytes_progress"] == 512
