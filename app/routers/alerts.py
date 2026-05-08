import structlog
from fastapi import APIRouter, HTTPException

from app.config import Settings
from app.dbus_client import JamiDBusClient
from app.schemas.alert import AlertNotification, AlertResult

router = APIRouter()
logger = structlog.get_logger()
settings = Settings()


def _format_alert_message(notification: AlertNotification) -> str:
    webhook = notification.webhook
    lines: list[str] = []

    status_emoji = "\u26a0\ufe0f" if webhook.status == "firing" else "\u2705"
    lines.append(f"{status_emoji} AlertManager: {webhook.status.upper()}")
    lines.append(f"Receiver: {webhook.receiver}")
    lines.append("")

    for i, alert in enumerate(webhook.alerts, 1):
        alert_icon = "\U0001f534" if alert.status == "firing" else "\U0001f7e2"
        lines.append(f"{alert_icon} Alert #{i} [{alert.status.upper()}]")

        if alert.labels:
            for key, value in alert.labels.items():
                lines.append(f"  {key}: {value}")

        if alert.annotations.get("summary"):
            lines.append(f"  Summary: {alert.annotations['summary']}")
        if alert.annotations.get("description"):
            lines.append(f"  Description: {alert.annotations['description']}")

        if alert.starts_at:
            lines.append(f"  Started: {alert.starts_at}")

        lines.append("")

    if webhook.external_url:
        lines.append(f"External URL: {webhook.external_url}")

    return "\n".join(lines)


@router.post("/alerts", response_model=AlertResult)
async def receive_alert(notification: AlertNotification) -> AlertResult:
    account_id = notification.account_id or settings.alert_account_id
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")

    recipients = notification.recipients
    if not recipients and settings.alert_recipients:
        recipients = settings.alert_recipients

    conversation_id = notification.conversation_id or settings.alert_conversation_id

    client = JamiDBusClient.get_instance()

    message = _format_alert_message(notification)

    sent = 0
    failed = 0
    details: list[dict[str, str]] = []

    if conversation_id:
        try:
            client.send_conversation_message(account_id, conversation_id, message)
            sent += 1
            details.append({"conversation_id": conversation_id, "status": "sent"})
            logger.info("alert_sent_to_conversation", conversation_id=conversation_id)
        except Exception as e:
            failed += 1
            details.append(
                {
                    "conversation_id": conversation_id,
                    "status": "failed",
                    "error": str(e),
                }
            )
            logger.error("alert_send_failed", conversation_id=conversation_id, error=str(e))
    elif recipients:
        for recipient in recipients:
            try:
                client.send_text_message(account_id, recipient, {"text/plain": message})
                sent += 1
                details.append({"recipient": recipient, "status": "sent"})
                logger.info("alert_sent_to_recipient", recipient=recipient)
            except Exception as e:
                failed += 1
                details.append({"recipient": recipient, "status": "failed", "error": str(e)})
                logger.error("alert_send_failed", recipient=recipient, error=str(e))
    else:
        raise HTTPException(status_code=400, detail="conversation_id or recipients are required")

    return AlertResult(
        status="ok" if failed == 0 else "partial" if sent > 0 else "error",
        sent=sent,
        failed=failed,
        details=details,
    )
