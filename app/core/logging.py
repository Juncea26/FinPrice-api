"""
Sistema de logging estructurado en formato JSON con métricas de tiempo de ejecución.
"""
import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """
    Formateador de logs que serializa cada registro como un objeto JSON estructurado,
    ideal para agregadores como Datadog, CloudWatch, GCP Cloud Logging o Loki.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Incluir campos adicionales si existen en record.__dict__
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message"
        }

        extra_data = {
            k: v for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith("_")
        }
        if extra_data:
            log_obj["extra"] = extra_data

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(log_level: str = "INFO") -> None:
    """Configura el handler raíz con JSONFormatter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Evitar duplicar handlers en reinicios
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(console_handler)

    # Silenciar logs ruidosos de librerías externas si es necesario
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retorna una instancia configurada de logger para el módulo dado."""
    return logging.getLogger(f"finprice.{name}")


# Inicializar al importar
setup_logging()
logger = get_logger("core")
