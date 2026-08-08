"""Configuracion del puente TradingView -> MetaTrader 5.

Las credenciales NUNCA se escriben en el repositorio: se leen de variables de
entorno (ver `bridge/.env.example`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_SYMBOLS = ("XAUUSD", "XAGUSD")


class ConfigError(RuntimeError):
    """Falta configuracion obligatoria o es invalida."""


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"Falta la variable de entorno {name}. Copia bridge/.env.example a .env y complétala."
        )
    return value


@dataclass(frozen=True)
class Settings:
    login: int
    password: str
    server: str
    terminal_path: str | None
    webhook_secret: str
    allowed_symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    max_lots: float = 1.0
    deviation_points: int = 20
    magic: int = 20260807
    dry_run: bool = False
    symbol_suffix: str = ""
    default_lots: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        symbols = os.environ.get("MT5_SYMBOLS", ",".join(DEFAULT_SYMBOLS))
        allowed = tuple(s.strip().upper() for s in symbols.split(",") if s.strip())
        try:
            login = int(_require("MT5_LOGIN"))
        except ValueError as exc:
            raise ConfigError("MT5_LOGIN debe ser numerico") from exc
        return cls(
            login=login,
            password=_require("MT5_PASSWORD"),
            server=_require("MT5_SERVER"),
            terminal_path=os.environ.get("MT5_TERMINAL_PATH") or None,
            webhook_secret=_require("WEBHOOK_SECRET"),
            allowed_symbols=allowed or DEFAULT_SYMBOLS,
            max_lots=float(os.environ.get("MAX_LOTS", "1.0")),
            deviation_points=int(os.environ.get("DEVIATION_POINTS", "20")),
            magic=int(os.environ.get("MAGIC", "20260807")),
            dry_run=os.environ.get("DRY_RUN", "false").strip().lower() in {"1", "true", "yes"},
            symbol_suffix=os.environ.get("SYMBOL_SUFFIX", ""),
        )

    def resolve_symbol(self, symbol: str) -> str:
        """Aplica el sufijo del broker (algunos usan XAUUSD.pro, XAUUSD_r, etc.)."""
        upper = symbol.strip().upper()
        return f"{upper}{self.symbol_suffix}"
