"""
Módulo de compatibilidad hacia el punto de entrada principal FastAPI (`main.py`).
Permite importar o levantar la aplicación tanto vía `main:app` como vía `app.main:app`.
"""
from main import (
    app,
    calculate_seconds_until_next_window,
    calculate_seconds_until_target,
    daily_scheduler_loop,
    keep_alive_self_ping_loop,
    lifespan,
)

__all__ = [
    "app",
    "lifespan",
    "daily_scheduler_loop",
    "keep_alive_self_ping_loop",
    "calculate_seconds_until_next_window",
    "calculate_seconds_until_target",
]
