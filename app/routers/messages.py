from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.dbus_client import JamiDBusClient
from app.schemas.message import MessageSend
from app.services.event_bus import EventBus
from app.websocket.handler import ConnectionManager

router = APIRouter()
ws_manager = ConnectionManager()

_event_bus: EventBus | None = None


def set_event_bus(bus: EventBus) -> None:
    global _event_bus
    _event_bus = bus


@router.post("/accounts/{account_id}/messages")
async def send_message(account_id: str, body: MessageSend) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    try:
        msg_id = client.send_text_message(account_id, body.to, {"text/plain": body.body})
        return {"message_id": msg_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/{account_id}/conversations/{conv_id}/messages")
async def send_conversation_message(
    account_id: str, conv_id: str, body: MessageSend
) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    try:
        client.send_conversation_message(account_id, conv_id, body.body)
        return {"status": "sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts/{account_id}/conversations")
async def list_conversations(account_id: str) -> list[str]:
    client = JamiDBusClient.get_instance()
    try:
        return client.get_conversations(account_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/accounts/{account_id}/conversation-requests")
async def list_conversation_requests(account_id: str) -> list[dict]:
    client = JamiDBusClient.get_instance()
    try:
        return client.get_conversation_requests(account_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/accounts/{account_id}/conversation-requests/{conv_id}/accept")
async def accept_conversation_request(account_id: str, conv_id: str) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    try:
        client.accept_conversation_request(account_id, conv_id)
        return {"status": "accepted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accounts/{account_id}/conversation-requests/{conv_id}/decline")
async def decline_conversation_request(account_id: str, conv_id: str) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    try:
        client.decline_conversation_request(account_id, conv_id)
        return {"status": "declined"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts/{account_id}/conversations/{conv_id}/messages")
async def get_conversation_messages(account_id: str, conv_id: str, count: int = 50) -> dict:
    client = JamiDBusClient.get_instance()
    try:
        client.load_conversation(account_id, conv_id, "", count)
        return {"status": "loaded", "count": count}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.websocket("/ws/accounts/{account_id}/events")
async def websocket_events(websocket: WebSocket, account_id: str) -> None:
    await ws_manager.connect(account_id, websocket)
    if _event_bus is None:
        await websocket.close()
        return
    queue = _event_bus.subscribe(account_id)
    try:
        while True:
            data = await queue.get()
            await websocket.send_json(data)
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(account_id, websocket)
        _event_bus.unsubscribe(account_id, queue)
