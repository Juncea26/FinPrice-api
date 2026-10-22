"""
Configuración centralizada de FinPrice API utilizando Pydantic Settings.
Soporta lectura desde variables de entorno y archivos .env.
"""
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Entorno
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "FinPrice API"
    VERSION: str = "2.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Seguridad y autenticación
    FINPRICE_ADMIN_API_KEY: str = "finprice_secret_admin_key_2026"
    ALLOWED_ORIGINS: Union[str, List[str]] = "*"

    # Base de datos y caché
    DATABASE_URL: str = "sqlite:///./finprice_cloud.db"
    CACHE_TTL_SECONDS: int = 60

    # Rate Limiting
    RATE_LIMIT_READ_PER_MINUTE: int = 60
    RATE_LIMIT_WRITE_PER_MINUTE: int = 5

    # Recolectores
    COLLECTION_INTERVAL_MINUTES: int = 360  # 6 horas por defecto
    COLLECTOR_TIMEOUT_CONNECT: float = 5.0
    COLLECTOR_TIMEOUT_READ: float = 10.0
    COLLECTOR_MAX_CONCURRENCY: int = 4
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 120

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v == "*":
                return ["*"]
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


settings = Settings()
