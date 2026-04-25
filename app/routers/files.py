from fastapi import APIRouter, HTTPException

from app.dbus_client import JamiDBusClient
from app.schemas.file import FileDownload, FileSend

router = APIRouter()


@router.post("/accounts/{account_id}/files/send")
async def send_file(account_id: str, body: FileSend) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    try:
        interaction_id = client.send_file(account_id, body.conversation_id, body.file_path)
        return {"interaction_id": interaction_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/{account_id}/files/download")
async def download_file(account_id: str, body: FileDownload) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    try:
        client.download_file(account_id, body.conversation_id, body.interaction_id, body.file_path)
        return {"status": "downloading"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts/{account_id}/files/{conversation_id}/{interaction_id}/status")
async def file_status(account_id: str, conversation_id: str, interaction_id: str) -> dict:
    client = JamiDBusClient.get_instance()
    try:
        info = client.file_transfer_info(account_id, conversation_id, interaction_id)
        return info
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
