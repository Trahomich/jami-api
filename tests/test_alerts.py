from unittest.mock import patch

import pytest

from app.schemas.alert import Alert, AlertManagerWebhook, AlertNotification


def _make_webhook(
    status: str = "firing",
    alerts: list[Alert] | None = None,
) -> AlertManagerWebhook:
    if alerts is None:
        alerts = [
            Alert(
                status="firing",
                labels={"alertname": "HighCpu", "severity": "critical"},
                annotations={"summary": "CPU > 90%", "description": "Node cpu usage too high"},
                starts_at="2026-01-01T00:00:00Z",
            )
        ]
    return AlertManagerWebhook(
        receiver="jami",
        status=status,
        alerts=alerts,
        common_labels={"alertname": "HighCpu"},
        external_url="http://alertmanager:9093",
    )


@pytest.mark.asyncio
async def test_send_alert_to_conversation(mock_dbus_client):
    with patch("app.routers.alerts.JamiDBusClient.get_instance", return_value=mock_dbus_client):
        from app.routers.alerts import receive_alert

        notification = AlertNotification(
            account_id="acc1",
            conversation_id="conv1",
            webhook=_make_webhook(),
        )
        result = await receive_alert(notification)

    assert result.status == "ok"
    assert result.sent == 1
    assert result.failed == 0
    mock_dbus_client.proxy.sendMessage.assert_called_once()
    call_args = mock_dbus_client.proxy.sendMessage.call_args[0]
    assert call_args[0] == "acc1"
    assert call_args[1] == "conv1"
    assert "FIRING" in call_args[2]


@pytest.mark.asyncio
async def test_send_alert_to_recipients(mock_dbus_client):
    with patch("app.routers.alerts.JamiDBusClient.get_instance", return_value=mock_dbus_client):
        from app.routers.alerts import receive_alert

        notification = AlertNotification(
            account_id="acc1",
            recipients=["jami://hash1", "jami://hash2"],
            webhook=_make_webhook(),
        )
        result = await receive_alert(notification)

    assert result.status == "ok"
    assert result.sent == 2
    assert result.failed == 0
    assert mock_dbus_client.proxy.sendTextMessage.call_count == 2


@pytest.mark.asyncio
async def test_send_resolved_alert(mock_dbus_client):
    with patch("app.routers.alerts.JamiDBusClient.get_instance", return_value=mock_dbus_client):
        from app.routers.alerts import receive_alert

        notification = AlertNotification(
            account_id="acc1",
            conversation_id="conv1",
            webhook=_make_webhook(
                status="resolved",
                alerts=[
                    Alert(
                        status="resolved",
                        labels={"alertname": "HighCpu", "severity": "warning"},
                        annotations={"summary": "CPU back to normal"},
                        starts_at="2026-01-01T00:00:00Z",
                        ends_at="2026-01-01T00:05:00Z",
                    )
                ],
            ),
        )
        result = await receive_alert(notification)

    assert result.status == "ok"
    assert result.sent == 1
    call_args = mock_dbus_client.proxy.sendMessage.call_args[0]
    assert "RESOLVED" in call_args[2]


@pytest.mark.asyncio
async def test_send_alert_no_account_id():
    with patch("app.routers.alerts.settings") as mock_settings:
        mock_settings.alert_account_id = ""
        mock_settings.alert_recipients = []

        from fastapi import HTTPException

        from app.routers.alerts import receive_alert

        notification = AlertNotification(
            webhook=_make_webhook(),
        )
        try:
            await receive_alert(notification)
            assert False, "Expected HTTPException"
        except HTTPException as e:
            assert e.status_code == 400
            assert "account_id" in e.detail


@pytest.mark.asyncio
async def test_send_alert_no_recipients():
    with patch("app.routers.alerts.settings") as mock_settings:
        mock_settings.alert_account_id = "acc1"
        mock_settings.alert_recipients = []

        from fastapi import HTTPException

        from app.routers.alerts import receive_alert

        notification = AlertNotification(
            account_id="acc1",
            webhook=_make_webhook(),
        )
        try:
            await receive_alert(notification)
            assert False, "Expected HTTPException"
        except HTTPException as e:
            assert e.status_code == 400
            assert "recipients" in e.detail or "conversation_id" in e.detail


@pytest.mark.asyncio
async def test_send_alert_partial_failure(mock_dbus_client):
    mock_dbus_client.proxy.sendTextMessage.side_effect = [
        "msg-1",
        RuntimeError("boom"),
    ]

    with patch("app.routers.alerts.JamiDBusClient.get_instance", return_value=mock_dbus_client):
        from app.routers.alerts import receive_alert

        notification = AlertNotification(
            account_id="acc1",
            recipients=["jami://hash1", "jami://hash2"],
            webhook=_make_webhook(),
        )
        result = await receive_alert(notification)

    assert result.status == "partial"
    assert result.sent == 1
    assert result.failed == 1


@pytest.mark.asyncio
async def test_send_alert_uses_config_defaults(mock_dbus_client):
    with patch("app.routers.alerts.JamiDBusClient.get_instance", return_value=mock_dbus_client):
        with patch("app.routers.alerts.settings") as mock_settings:
            mock_settings.alert_account_id = "default-acc"
            mock_settings.alert_recipients = ["jami://default1"]

            from app.routers.alerts import receive_alert

            notification = AlertNotification(
                webhook=_make_webhook(),
            )
            result = await receive_alert(notification)

    assert result.status == "ok"
    assert result.sent == 1
    call_args = mock_dbus_client.proxy.sendTextMessage.call_args[0]
    assert call_args[0] == "default-acc"


@pytest.mark.asyncio
async def test_format_multiple_alerts(mock_dbus_client):
    with patch("app.routers.alerts.JamiDBusClient.get_instance", return_value=mock_dbus_client):
        from app.routers.alerts import receive_alert

        notification = AlertNotification(
            account_id="acc1",
            conversation_id="conv1",
            webhook=_make_webhook(
                alerts=[
                    Alert(
                        status="firing",
                        labels={"alertname": "HighCpu", "severity": "critical"},
                        annotations={"summary": "CPU > 90%"},
                        starts_at="2026-01-01T00:00:00Z",
                    ),
                    Alert(
                        status="firing",
                        labels={"alertname": "HighMemory", "severity": "warning"},
                        annotations={"summary": "Memory > 80%"},
                        starts_at="2026-01-01T00:01:00Z",
                    ),
                ],
            ),
        )
        result = await receive_alert(notification)

    assert result.status == "ok"
    call_args = mock_dbus_client.proxy.sendMessage.call_args[0]
    body = call_args[2]
    assert "HighCpu" in body
    assert "HighMemory" in body
