from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    APP_ENV: str = "development"
    APP_NAME: str = "VIGIA"
    LOG_LEVEL: str = "INFO"
    CORS_ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    VIGIA_ENABLE_LIVE_DATA: bool = True
    VIGIA_CODE_COMMIT: str = "unavailable"
    SUPABASE_DB_URL: SecretStr | None = None
    NASA_FIRMS_MAP_KEY: SecretStr | None = None
    AEMET_API_KEY: SecretStr | None = None
    EUMETSAT_CONSUMER_KEY: SecretStr | None = None
    EUMETSAT_CONSUMER_SECRET: SecretStr | None = None
    EUMETSAT_MTG_FIR_COLLECTION: str = "EO:EUM:DAT:0682"
    EUMETSAT_API_BASE_URL: str = "https://api.eumetsat.int"
    COPERNICUS_CLIENT_ID: SecretStr | None = None
    COPERNICUS_CLIENT_SECRET: SecretStr | None = None
    COPERNICUS_TOKEN_URL: str = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"  # noqa: S105
        "protocol/openid-connect/token"
    )
    COPERNICUS_SH_BASE_URL: str = "https://sh.dataspace.copernicus.eu"

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
