import pytest


@pytest.mark.parametrize(
    "pocs,esperado",
    [
        ({"5m": 2635.0, "15m": 2634.8, "1h": 2635.2}, True),
        ({"5m": 2635.0, "15m": 2637.0}, True),  # rango exactamente igual a la tolerancia
        ({"5m": 2635.0, "15m": 2637.01}, False),
        ({"5m": 2635.0}, True),
    ],
)
def test_poc_multi_tf_alineado(smc, pocs, esperado):
    assert smc.poc_multi_tf_alineado(pocs) is esperado


def test_pocs_no_alineados_devuelve_rango(smc):
    resultado = smc.validar_senal_smc("BUY", 2640.0, {"5m": 2630.0, "1h": 2640.0})
    assert resultado["valida"] is False
    assert resultado["rango_pocs"] == pytest.approx(10.0)


@pytest.mark.parametrize(
    "direccion,precio,valida",
    [
        ("BUY", 2636.0, True),
        ("buy", 2636.0, True),
        ("BUY", 2635.0, False),  # precio igual al POC promedio
        ("BUY", 2630.0, False),
        ("SELL", 2634.0, True),
        ("sell", 2634.0, True),
        ("SELL", 2635.0, False),
        ("SELL", 2640.0, False),
    ],
)
def test_validar_senal_smc_direcciones(smc, direccion, precio, valida):
    pocs = {"5m": 2635.0, "15m": 2635.0, "1h": 2635.0}
    resultado = smc.validar_senal_smc(direccion, precio, pocs)
    assert resultado["valida"] is valida
    assert resultado["motivo"]


def test_validar_senal_smc_direccion_desconocida(smc):
    resultado = smc.validar_senal_smc("HOLD", 2635.0, {"5m": 2635.0})
    assert resultado["valida"] is False
    assert "Dirección no reconocida" in resultado["motivo"]
