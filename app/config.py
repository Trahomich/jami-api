from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"
    dbus_address: str = ""

    model_config = {"env_prefix": "JAMI_API_"}
