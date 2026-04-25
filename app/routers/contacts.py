from fastapi import APIRouter, HTTPException

from app.dbus_client import JamiDBusClient
from app.schemas.contact import ContactAdd

router = APIRouter()


@router.get("/accounts/{account_id}/contacts")
async def list_contacts(account_id: str) -> list[dict]:
    client = JamiDBusClient.get_instance()
    try:
        return client.get_contacts(account_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/accounts/{account_id}/contacts")
async def add_contact(account_id: str, body: ContactAdd) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    client.add_contact(account_id, body.uri)
    return {"status": "added"}


@router.delete("/accounts/{account_id}/contacts/{uri}")
async def remove_contact(account_id: str, uri: str) -> dict[str, str]:
    client = JamiDBusClient.get_instance()
    client.remove_contact(account_id, uri)
    return {"status": "removed"}


@router.get("/accounts/{account_id}/contacts/{uri}")
async def get_contact(account_id: str, uri: str) -> dict:
    client = JamiDBusClient.get_instance()
    try:
        return client.get_contact_details(account_id, uri)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
