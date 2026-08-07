"""Envio de ordenes a MetaTrader 5 (Swissquote).

El paquete `MetaTrader5` solo existe en Windows, por eso se importa de forma
perezosa: el resto del puente (y sus tests) funciona en cualquier plataforma.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

from bridge.config import Settings
from bridge.models import TradeSignal

logger = logging.getLogger(__name__)


class OrderError(RuntimeError):
    """El broker rechazo la orden o el terminal no esta disponible."""


class Mt5Module(Protocol):
    """Subconjunto de la API de MetaTrader5 que usa el puente."""

    TRADE_ACTION_DEAL: int
    ORDER_TYPE_BUY: int
    ORDER_TYPE_SELL: int
    ORDER_TIME_GTC: int
    ORDER_FILLING_IOC: int
    TRADE_RETCODE_DONE: int

    def initialize(self, *args: Any, **kwargs: Any) -> bool: ...
    def shutdown(self) -> None: ...
    def last_error(self) -> tuple[int, str]: ...
    def symbol_info(self, symbol: str) -> Any: ...
    def symbol_info_tick(self, symbol: str) -> Any: ...
    def symbol_select(self, symbol: str, enable: bool) -> bool: ...
    def order_send(self, request: dict[str, Any]) -> Any: ...


def _import_mt5() -> Mt5Module:
    try:
        import MetaTrader5 as mt5  # noqa: N813
    except ImportError as exc:  # pragma: no cover - depende de la plataforma
        raise OrderError(
            "El paquete MetaTrader5 no esta instalado (solo Windows). "
            "Instala con: pip install MetaTrader5"
        ) from exc
    return mt5


class Mt5Client:
    """Cliente con conexion perezosa y reintento de inicializacion."""

    def __init__(self, settings: Settings, mt5: Mt5Module | None = None) -> None:
        self._settings = settings
        self._mt5 = mt5
        self._connected = False
        self._lock = threading.Lock()

    @property
    def mt5(self) -> Mt5Module:
        if self._mt5 is None:
            self._mt5 = _import_mt5()
        return self._mt5

    def connect(self) -> None:
        with self._lock:
            if self._connected:
                return
            kwargs: dict[str, Any] = {
                "login": self._settings.login,
                "password": self._settings.password,
                "server": self._settings.server,
            }
            if self._settings.terminal_path:
                kwargs["path"] = self._settings.terminal_path
            if not self.mt5.initialize(**kwargs):
                code, message = self.mt5.last_error()
                raise OrderError(f"No se pudo inicializar MT5 ({code}): {message}")
            self._connected = True
            logger.info("Conectado a MT5 %s (cuenta %s)", self._settings.server, self._settings.login)

    def disconnect(self) -> None:
        with self._lock:
            if self._connected:
                self.mt5.shutdown()
                self._connected = False

    def _ensure_symbol(self, symbol: str) -> Any:
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise OrderError(f"Simbolo desconocido en el broker: {symbol}")
        if not getattr(info, "visible", True):
            self.mt5.symbol_select(symbol, True)
            info = self.mt5.symbol_info(symbol)
        return info

    def _clamp_volume(self, info: Any, lots: float) -> float:
        step = getattr(info, "volume_step", 0.01) or 0.01
        minimum = getattr(info, "volume_min", step)
        maximum = min(getattr(info, "volume_max", self._settings.max_lots), self._settings.max_lots)
        volume = max(minimum, min(lots, maximum))
        # Redondea al step del broker para evitar rechazos por volumen invalido.
        steps = round(volume / step)
        volume = round(steps * step, 8)
        return max(minimum, min(volume, maximum))

    def send_order(self, signal: TradeSignal) -> dict[str, Any]:
        symbol = self._settings.resolve_symbol(signal.symbol)
        if signal.symbol not in self._settings.allowed_symbols:
            raise OrderError(f"Simbolo no permitido: {signal.symbol}")

        if self._settings.dry_run:
            logger.warning("DRY_RUN activo: no se envia la orden %s %s", signal.action, symbol)
            return {"dry_run": True, "symbol": symbol, "action": signal.action, "lots": signal.lots}

        self.connect()
        info = self._ensure_symbol(symbol)
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise OrderError(f"Sin cotizacion para {symbol}")

        is_buy = signal.action == "BUY"
        price = tick.ask if is_buy else tick.bid
        request: dict[str, Any] = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": self._clamp_volume(info, signal.lots),
            "type": self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": self._settings.deviation_points,
            "magic": self._settings.magic,
            "comment": signal.comment[:31],
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        if signal.sl is not None:
            request["sl"] = signal.sl
        if signal.tp is not None:
            request["tp"] = signal.tp

        result = self.mt5.order_send(request)
        if result is None:
            code, message = self.mt5.last_error()
            raise OrderError(f"order_send devolvio None ({code}): {message}")
        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            raise OrderError(
                f"Orden rechazada retcode={result.retcode} comment={getattr(result, 'comment', '')}"
            )
        return {
            "order": getattr(result, "order", None),
            "deal": getattr(result, "deal", None),
            "volume": getattr(result, "volume", request["volume"]),
            "price": getattr(result, "price", price),
            "symbol": symbol,
            "action": signal.action,
        }
