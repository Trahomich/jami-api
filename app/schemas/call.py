from typing import Any

from pydantic import BaseModel


class CallCreate(BaseModel):
    to: str


class CallInfo(BaseModel):
    id: str
    details: dict[str, Any] = {}
