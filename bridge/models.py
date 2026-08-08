"""Modelos del payload que envia la alerta de TradingView."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class TradeSignal(BaseModel):
    """Senal operativa (BUY/SELL) emitida por la estrategia Pine."""

    action: Literal["BUY", "SELL"]
    symbol: str
    lots: float = Field(gt=0)
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    poc_cluster_low: Optional[float] = None
    poc_cluster_high: Optional[float] = None
    poc_count: Optional[int] = None
    retrace_pct: Optional[float] = None
    entry_mode: Optional[str] = None
    tf: Optional[str] = None
    comment: str = "POC cluster pullback"

    @field_validator("action", mode="before")
    @classmethod
    def _upper_action(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("symbol", mode="before")
    @classmethod
    def _upper_symbol(cls, value: object) -> object:
        return value.upper().strip() if isinstance(value, str) else value

    @field_validator("sl", "tp", "price", "retrace_pct", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        # Pine escribe "NaN" cuando el valor no aplica.
        if isinstance(value, str) and value.strip().lower() in {"", "na", "nan"}:
            return None
        return value


class CorrectionEvent(BaseModel):
    """Aviso informativo del inicio de una correccion (no ejecuta ordenes)."""

    event: Literal["correction_start"]
    direction: Literal["UP", "DOWN"]
    symbol: str
    price: Optional[float] = None
    impulse_from: Optional[float] = None
    impulse_to: Optional[float] = None
    poc_cluster_low: Optional[float] = None
    poc_cluster_high: Optional[float] = None
    tf: Optional[str] = None
