from typing import Any

from pydantic import BaseModel


class Alert(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}
    starts_at: str = ""
    ends_at: str = ""
    generator_url: str = ""
    fingerprint: str = ""


class AlertManagerWebhook(BaseModel):
    receiver: str = ""
    status: str = "firing"
    alerts: list[Alert] = []
    group_labels: dict[str, str] = {}
    common_labels: dict[str, str] = {}
    common_annotations: dict[str, str] = {}
    external_url: str = ""
    version: str = "4"
    group_key: str = ""


class AlertNotification(AlertManagerWebhook):
    account_id: str | None = None
    conversation_id: str | None = None
    recipients: list[str] | None = None


class AlertResult(BaseModel):
    status: str
    sent: int
    failed: int
    details: list[dict[str, Any]] = []
