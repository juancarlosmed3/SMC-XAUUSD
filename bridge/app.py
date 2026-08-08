"""Puente webhook TradingView -> MetaTrader 5 (Swissquote).

Uso:
    set -a && source bridge/.env && set +a
    uvicorn bridge.app:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

from bridge.config import ConfigError, Settings
from bridge.models import CorrectionEvent, TradeSignal
from bridge.mt5_client import Mt5Client, OrderError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("bridge")

_settings: Settings | None = None
_client: Mt5Client | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    if _client is not None:
        _client.disconnect()


app = FastAPI(title="Puente TradingView -> MT5", version="1.0", lifespan=lifespan)


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def get_client() -> Mt5Client:
    global _client
    if _client is None:
        _client = Mt5Client(get_settings())
    return _client


def _check_secret(settings: Settings, provided: str | None) -> None:
    if not provided or not hmac.compare_digest(provided, settings.webhook_secret):
        raise HTTPException(status_code=401, detail="Secreto de webhook invalido")


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        settings = get_settings()
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "ok": True,
        "server": settings.server,
        "symbols": list(settings.allowed_symbols),
        "dry_run": settings.dry_run,
    }


@app.post("/webhook")
async def webhook(
    request: Request,
    secret: str | None = None,
    x_webhook_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    """Recibe el JSON de la alerta de TradingView.

    TradingView no permite headers personalizados en sus webhooks, asi que el
    secreto se acepta tambien como query param (`/webhook?secret=...`).
    Acepta senales operativas (`action`) y avisos de inicio de correccion
    (`event=correction_start`), que solo se registran.
    """
    try:
        settings = get_settings()
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _check_secret(settings, x_webhook_secret or secret)

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Cuerpo no es JSON valido") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="El JSON debe ser un objeto")

    if payload.get("event") == "correction_start":
        event = CorrectionEvent.model_validate(payload)
        logger.info(
            "Inicio de correccion %s en %s (%s) precio=%s cluster=%s-%s",
            event.direction, event.symbol, event.tf, event.price,
            event.poc_cluster_low, event.poc_cluster_high,
        )
        return {"status": "notificado", "event": "correction_start", "direction": event.direction}

    signal = TradeSignal.model_validate(payload)
    if signal.symbol not in settings.allowed_symbols:
        raise HTTPException(status_code=400, detail=f"Simbolo no permitido: {signal.symbol}")
    if signal.lots > settings.max_lots:
        raise HTTPException(
            status_code=400, detail=f"Lotes {signal.lots} superan el maximo {settings.max_lots}"
        )

    try:
        result = get_client().send_order(signal)
    except OrderError as exc:
        logger.error("Fallo al enviar la orden: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    logger.info("Orden ejecutada: %s", result)
    return {"status": "ejecutada", "result": result}
