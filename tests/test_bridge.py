from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bridge import app as app_module
from bridge.config import Settings
from bridge.models import TradeSignal
from bridge.mt5_client import Mt5Client, OrderError

SECRET = "secreto-de-prueba"


class FakeMt5:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009

    def __init__(self, retcode: int | None = None) -> None:
        self.retcode = retcode if retcode is not None else self.TRADE_RETCODE_DONE
        self.requests: list[dict[str, Any]] = []
        self.initialized = False

    def initialize(self, **kwargs: Any) -> bool:
        self.initialized = True
        return True

    def shutdown(self) -> None:
        self.initialized = False

    def last_error(self) -> tuple[int, str]:
        return (0, "ok")

    def symbol_info(self, symbol: str) -> Any:
        return SimpleNamespace(visible=True, volume_step=0.01, volume_min=0.01, volume_max=10.0)

    def symbol_info_tick(self, symbol: str) -> Any:
        return SimpleNamespace(ask=2635.5, bid=2635.2)

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        return True

    def order_send(self, request: dict[str, Any]) -> Any:
        self.requests.append(request)
        return SimpleNamespace(retcode=self.retcode, order=1, deal=2, volume=request["volume"],
                               price=request["price"], comment="done")


def make_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = dict(
        login=6190344,
        password="x",
        server="Swissquote-Server",
        terminal_path=None,
        webhook_secret=SECRET,
        max_lots=1.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeMt5]:
    settings = make_settings()
    fake = FakeMt5()
    monkeypatch.setattr(app_module, "_settings", settings)
    monkeypatch.setattr(app_module, "_client", Mt5Client(settings, mt5=fake))
    return TestClient(app_module.app), fake


def test_webhook_rejects_wrong_secret(client: tuple[TestClient, FakeMt5]) -> None:
    api, _ = client
    resp = api.post("/webhook", json={"action": "BUY", "symbol": "XAUUSD", "lots": 0.1},
                    headers={"X-Webhook-Secret": "malo"})
    assert resp.status_code == 401


def test_webhook_executes_buy(client: tuple[TestClient, FakeMt5]) -> None:
    api, fake = client
    payload = {"action": "buy", "symbol": "xauusd", "lots": 0.1, "sl": 2630.0, "tp": 2646.0}
    resp = api.post(f"/webhook?secret={SECRET}", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ejecutada"
    sent = fake.requests[-1]
    assert sent["symbol"] == "XAUUSD"
    assert sent["type"] == FakeMt5.ORDER_TYPE_BUY
    assert sent["price"] == 2635.5
    assert sent["sl"] == 2630.0


def test_webhook_sell_uses_bid(client: tuple[TestClient, FakeMt5]) -> None:
    api, fake = client
    resp = api.post("/webhook", json={"action": "SELL", "symbol": "XAGUSD", "lots": 0.2},
                    headers={"X-Webhook-Secret": SECRET})
    assert resp.status_code == 200
    assert fake.requests[-1]["price"] == 2635.2
    assert fake.requests[-1]["type"] == FakeMt5.ORDER_TYPE_SELL


def test_webhook_rejects_unknown_symbol(client: tuple[TestClient, FakeMt5]) -> None:
    api, _ = client
    resp = api.post("/webhook", json={"action": "BUY", "symbol": "EURUSD", "lots": 0.1},
                    headers={"X-Webhook-Secret": SECRET})
    assert resp.status_code == 400


def test_webhook_rejects_excess_lots(client: tuple[TestClient, FakeMt5]) -> None:
    api, _ = client
    resp = api.post("/webhook", json={"action": "BUY", "symbol": "XAUUSD", "lots": 5},
                    headers={"X-Webhook-Secret": SECRET})
    assert resp.status_code == 400


def test_correction_event_is_only_logged(client: tuple[TestClient, FakeMt5]) -> None:
    api, fake = client
    payload = {"event": "correction_start", "direction": "DOWN", "symbol": "XAUUSD",
               "price": 2640.0, "tf": "15"}
    resp = api.post("/webhook", json=payload, headers={"X-Webhook-Secret": SECRET})
    assert resp.status_code == 200
    assert resp.json()["status"] == "notificado"
    assert fake.requests == []


def test_pine_nan_fields_become_none() -> None:
    signal = TradeSignal.model_validate(
        {"action": "BUY", "symbol": "XAUUSD", "lots": 0.1, "sl": "NaN", "tp": "NaN"}
    )
    assert signal.sl is None and signal.tp is None


def test_dry_run_does_not_send() -> None:
    fake = FakeMt5()
    client_ = Mt5Client(make_settings(dry_run=True), mt5=fake)
    result = client_.send_order(TradeSignal(action="BUY", symbol="XAUUSD", lots=0.1))
    assert result["dry_run"] is True
    assert fake.requests == []


def test_rejected_retcode_raises() -> None:
    fake = FakeMt5(retcode=10016)
    client_ = Mt5Client(make_settings(), mt5=fake)
    with pytest.raises(OrderError):
        client_.send_order(TradeSignal(action="BUY", symbol="XAUUSD", lots=0.1))


def test_volume_is_clamped_to_max_lots() -> None:
    fake = FakeMt5()
    client_ = Mt5Client(make_settings(max_lots=0.5), mt5=fake)
    client_.send_order(TradeSignal(action="BUY", symbol="XAUUSD", lots=0.49))
    assert fake.requests[-1]["volume"] == pytest.approx(0.49)
