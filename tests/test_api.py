def test_home(client):
    respuesta = client.get("/")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"mensaje": "API SMC Scalping activa - XAU/USD"}


def test_estado_xau(client, smc):
    cuerpo = client.get("/estado_xau").json()
    assert cuerpo["pocs_referencia"] == smc.POC_REFERENCIA
    assert cuerpo["alineacion_tolerancia_usd"] == smc.ALINEACION_TOLERANCIA
    assert set(cuerpo["reglas"]) == {"buy", "sell"}


def _senal(**overrides):
    senal = {
        "activo": "XAUUSD",
        "timeframe": "5m",
        "direccion": "BUY",
        "precio_actual": 2636.0,
        "pocs": {"5m": 2635.0, "15m": 2634.8, "1h": 2635.2},
    }
    senal.update(overrides)
    return senal


def test_validar_senal_valida(client):
    respuesta = client.post("/validar_senal", json=_senal())
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["resultado"]["valida"] is True
    assert cuerpo["senal_recibida"]["activo"] == "XAUUSD"


def test_validar_senal_invalida_por_precio(client):
    cuerpo = client.post("/validar_senal", json=_senal(precio_actual=2630.0)).json()
    assert cuerpo["resultado"]["valida"] is False


def test_validar_senal_activo_no_soportado(client):
    respuesta = client.post("/validar_senal", json=_senal(activo="EURUSD"))
    assert respuesta.status_code == 400
    assert respuesta.json()["detail"] == "Solo se acepta XAUUSD"


def test_validar_senal_activo_minusculas_aceptado(client):
    assert client.post("/validar_senal", json=_senal(activo="xauusd")).status_code == 200


def test_validar_senal_payload_incompleto(client):
    senal = _senal()
    del senal["precio_actual"]
    assert client.post("/validar_senal", json=senal).status_code == 422
