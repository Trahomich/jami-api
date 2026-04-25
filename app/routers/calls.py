from fastapi import APIRouter, HTTPException

from app.dbus_client import JamiDBusClient
from app.schemas.call import CallCreate

router = APIRouter()


@router.post("/accounts/{account_id}/calls")
async def place_call(account_id: str, body: CallCreate) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    try:
        call_id = client.place_call(account_id, body.to)
        return {"call_id": call_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/{account_id}/calls/{call_id}/accept")
async def accept_call(account_id: str, call_id: str) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    try:
        client.accept_call(account_id, call_id)
        return {"status": "accepted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/{account_id}/calls/{call_id}/hangup")
async def hangup_call(account_id: str, call_id: str) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    try:
        client.hang_up(account_id, call_id)
        return {"status": "hungup"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts/{account_id}/calls")
async def list_calls(account_id: str) -> list[dict]:
    client = JamiDBusClient.get_instance()
    try:
        return client.get_call_list(account_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
