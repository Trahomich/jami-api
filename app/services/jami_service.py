from typing import Any

from app.dbus_client import JamiDBusClient


class JamiService:
    def __init__(self, client: JamiDBusClient | None = None) -> None:
        self._client = client or JamiDBusClient.get_instance()

    @property
    def dbus(self) -> JamiDBusClient:
        return self._client

    def create_account(self, alias: str = "") -> str:
        details: dict[str, str] = {
            "Account.type": "RING",
            "Account.alias": alias,
            "Account.archivePassword": "",
            "Account.archivePIN": "",
        }
        return self.dbus.add_account(details)

    def delete_account(self, account_id: str) -> None:
        self.dbus.remove_account(account_id)

    def list_accounts(self) -> list[str]:
        return self.dbus.get_account_list()

    def get_account_info(self, account_id: str) -> dict[str, Any]:
        details = self.dbus.get_account_details(account_id)
        volatile = self.dbus.get_volatile_account_details(account_id)
        return {
            "id": account_id,
            "details": details,
            "volatile": volatile,
        }

    def register_name(self, account_id: str, name: str, password: str = "") -> int:
        return self.dbus.register_name(account_id, name, password)
