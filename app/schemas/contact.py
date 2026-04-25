from typing import Any

from pydantic import BaseModel


class ContactAdd(BaseModel):
    uri: str


class ContactInfo(BaseModel):
    uri: str
    details: dict[str, Any] = {}
