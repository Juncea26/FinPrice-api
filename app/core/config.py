"""
Configuración centralizada de FinPrice API utilizando Pydantic Settings.
"""
import os
from typing import List, Optional, Union
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Entorno y servidor
    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "FinPrice API"
    VERSION: str = "2.1.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Seguridad y autenticación
    FINPRICE_ADMIN_API_KEY: str = "finprice_secret_admin_key_2026"
    FINPRICE_TOKEN_SECRET: str = "finprice_hmac_token_secret_key_2026"
    ALLOWED_ORIGINS: Union[str, List[str]] = "*"

    # Base de datos asíncrona real (lee de variable de entorno o .env, fallback a SQLite local)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./finprice.db")
    WRITER_DATABASE_URL: str = os.getenv("WRITER_DATABASE_URL", "")
    READER_DATABASE_URL: str = os.getenv("READER_DATABASE_URL", "")
    CACHE_TTL_SECONDS: int = 60

    # Rate Limiting (50 peticiones por minuto por IP)
    RATE_LIMIT_READ_PER_MINUTE: int = 50
    RATE_LIMIT_WRITE_PER_MINUTE: int = 5

    # Parámetros del motor de recolección en vivo (Optimizado para 512 MB RAM)
    ENABLE_INTERNAL_SCHEDULER: bool = True
    ENABLE_AUTO_CATEGORY_DISCOVERY: bool = True
    AUTO_CATEGORY_MAX_PAGES: int = 1
    COLLECTION_INTERVAL_MINUTES: int = 360  # Cada 6 horas por defecto
    COLLECTOR_TIMEOUT_CONNECT: float = 6.0
    COLLECTOR_TIMEOUT_READ: float = 12.0
    COLLECTOR_MAX_CONCURRENCY: int = 2
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 4
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 15

    # Proxy residencial peruano selectivo opcional (por defecto desactivado; DIRECT en todas las tiendas)
    PERU_PROXY_URL: Optional[str] = None
    PERU_PROXY_STORES: str = "ripley,efe,curacao"

    @field_validator("PERU_PROXY_URL", mode="before")
    @classmethod
    def parse_peru_proxy_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = str(v).strip()
        return cleaned if cleaned else None

    @field_validator("PERU_PROXY_STORES", mode="before")
    @classmethod
    def parse_peru_proxy_stores(cls, v: Union[str, List[str], None]) -> str:
        if v is None:
            return "ripley,efe,curacao"
        if isinstance(v, list):
            return ",".join(str(item).strip().lower() for item in v if str(item).strip())
        return str(v).strip()

    @field_validator("ENABLE_INTERNAL_SCHEDULER", mode="before")
    @classmethod
    def parse_enable_internal_scheduler(cls, v: Union[bool, str, int, None]) -> bool:
        if v is None:
            return True
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return bool(v)
        if isinstance(v, str):
            cleaned = v.strip().lower()
            if cleaned == "":
                return True
            if cleaned in {"true", "1", "yes", "on", "si", "sí"}:
                return True
            if cleaned in {"false", "0", "no", "off"}:
                return False
        return bool(v)

    @field_validator("ENABLE_AUTO_CATEGORY_DISCOVERY", mode="before")
    @classmethod
    def parse_enable_auto_category_discovery(cls, v: Union[bool, str, int, None]) -> bool:
        if v is None:
            return True
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return bool(v)
        if isinstance(v, str):
            cleaned = v.strip().lower()
            if cleaned == "":
                return True
            if cleaned in {"true", "1", "yes", "on", "si", "sí"}:
                return True
            if cleaned in {"false", "0", "no", "off"}:
                return False
        return bool(v)

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
