from typing import Any

from pydantic import BaseModel


class MessageSend(BaseModel):
    to: str
    body: str


class ConversationMessages(BaseModel):
    messages: list[dict[str, Any]]
