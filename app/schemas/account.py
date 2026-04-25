from pydantic import BaseModel


class AccountCreate(BaseModel):
    alias: str = ""


class AccountInfo(BaseModel):
    id: str
    details: dict[str, str]
    volatile: dict[str, str]


class AccountRegister(BaseModel):
    name: str
    password: str = ""
