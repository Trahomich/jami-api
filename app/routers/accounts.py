from fastapi import APIRouter, HTTPException

from app.schemas.account import AccountCreate, AccountInfo, AccountRegister
from app.services.jami_service import JamiService

router = APIRouter()


@router.post("/accounts", response_model=dict[str, str])
async def create_account(body: AccountCreate) -> dict[str, str]:
    service = JamiService()
    account_id = service.create_account(alias=body.alias)
    return {"id": account_id}


@router.get("/accounts", response_model=list[str])
async def list_accounts() -> list[str]:
    service = JamiService()
    return service.list_accounts()


@router.get("/accounts/{account_id}", response_model=AccountInfo)
async def get_account(account_id: str) -> AccountInfo:
    service = JamiService()
    try:
        info = service.get_account_info(account_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return AccountInfo(**info)


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str) -> dict[str, str]:
    service = JamiService()
    service.delete_account(account_id)
    return {"status": "deleted"}


@router.post("/accounts/{account_id}/register")
async def register_name(account_id: str, body: AccountRegister) -> dict[str, str]:
    service = JamiService()
    result = service.register_name(account_id, body.name, body.password)
    return {"result": str(result)}
