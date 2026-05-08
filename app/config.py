from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"
    dbus_address: str = ""
    alert_account_id: str = ""
    alert_conversation_id: str = ""
    alert_recipients: list[str] = []

    model_config = {"env_prefix": "JAMI_API_"}
