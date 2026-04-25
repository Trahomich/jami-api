from typing import Any

from pydantic import BaseModel


class FileSend(BaseModel):
    conversation_id: str
    file_path: str


class FileDownload(BaseModel):
    conversation_id: str
    interaction_id: str
    file_path: str


class FileInfo(BaseModel):
    info: dict[str, Any]
