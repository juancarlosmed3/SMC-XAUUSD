import logging
from typing import Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

logger = logging.getLogger("smc_xauusd")

app = FastAPI(title="API de Validación SMC - XAU/USD", version="1.0")

# --- Simulación de POCs alineados (en producción, vendrían de tu sistema o API externa) ---
# En scalping, usamos timeframe pequeño: 5m, 15m, 1h
POC_REFERENCIA = {
    "5m": 2635.0,
    "15m": 2634.8,
    "1h": 2635.2
}

# Alineación permitida: ±$2.0
ALINEACION_TOLERANCIA = 2.0

DIRECCIONES_VALIDAS = {"BUY", "SELL"}


def poc_multi_tf_alineado(pocs_recibidos: Dict[str, float]) -> bool:
    """Verifica si los POCs están alineados dentro de tolerancia.

    Lanza ValueError si el diccionario está vacío, ya que la alineación no
    puede evaluarse sin valores.
    """
    if not pocs_recibidos:
        raise ValueError("No se recibieron POCs para evaluar la alineación")
    valores = list(pocs_recibidos.values())
    rango = max(valores) - min(valores)
    return rango <= ALINEACION_TOLERANCIA


def validar_senal_smc(
    direccion: str,
    precio_actual: float,
    pocs: Dict[str, float]  # ej: {"5m": 2635, "15m": 2634.8, "1h": 2635.2}
) -> dict:
    """Valida señal según estrategia SMC Scalping.

    Lanza ValueError ante entradas inválidas (POCs vacíos o dirección
    desconocida) para que el error se propague al llamador en lugar de
    devolverse silenciosamente como una señal "no válida".
    """
    if not pocs:
        raise ValueError("No se recibieron POCs para validar la señal")

    direccion_norm = direccion.upper()
    if direccion_norm not in DIRECCIONES_VALIDAS:
        raise ValueError(f"Dirección no reconocida: '{direccion}' (usa BUY/SELL)")

    alineado = poc_multi_tf_alineado(pocs)

    if not alineado:
        return {
            "valida": False,
            "motivo": "POCs no alineados (rango excede tolerancia)",
            "rango_pocs": max(pocs.values()) - min(pocs.values())
        }

    # POC promedio para comparar
    poc_promedio = sum(pocs.values()) / len(pocs)

    if direccion_norm == "BUY":
        if precio_actual > poc_promedio:
            return {"valida": True, "motivo": "✅ BUY válida: POCs alineados + precio > POC"}
        return {"valida": False, "motivo": "❌ BUY inválida: precio NO supera POC"}

    # direccion_norm == "SELL"
    if precio_actual < poc_promedio:
        return {"valida": True, "motivo": "✅ SELL válida: POCs alineados + precio < POC"}
    return {"valida": False, "motivo": "❌ SELL inválida: precio NO está bajo POC"}


# --- Modelos de datos ---
class SenalSMC(BaseModel):
    activo: str
    timeframe: str
    direccion: str  # "BUY" o "SELL"
    precio_actual: float
    pocs: Dict[str, float]  # ej: {"5m": 2635.0, "15m": 2634.8, "1h": 2635.2}

    @field_validator("pocs")
    @classmethod
    def pocs_no_vacio(cls, v: Dict[str, float]) -> Dict[str, float]:
        if not v:
            raise ValueError("pocs no puede estar vacío")
        return v

    @field_validator("direccion")
    @classmethod
    def direccion_valida(cls, v: str) -> str:
        if v.upper() not in DIRECCIONES_VALIDAS:
            raise ValueError("direccion debe ser 'BUY' o 'SELL'")
        return v


# --- Manejo global de errores no esperados ---
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Evita que un error inesperado se propague como una traza opaca.

    Registra el error completo y responde con un 500 explícito.
    """
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Error interno del servidor"},
    )


# --- Endpoints ---
@app.get("/")
def home():
    return {"mensaje": "API SMC Scalping activa - XAU/USD"}


@app.post("/validar_senal")
def validar_senal(senal: SenalSMC):
    if senal.activo.upper() != "XAUUSD":
        raise HTTPException(status_code=400, detail="Solo se acepta XAUUSD")

    try:
        resultado = validar_senal_smc(
            direccion=senal.direccion,
            precio_actual=senal.precio_actual,
            pocs=senal.pocs
        )
    except ValueError as exc:
        # Errores de validación de dominio -> 400 con mensaje claro,
        # en lugar de devolverse silenciosamente como señal inválida.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "senal_recibida": senal.dict(),
        "resultado": resultado
    }


@app.get("/estado_xau")
def estado_actual():
    """Devuelve POCs de referencia y reglas (útil para ti o para IA)"""
    return {
        "activo": "XAU/USD",
        "estrategia": "SMC Scalping",
        "pocs_referencia": POC_REFERENCIA,
        "alineacion_tolerancia_usd": ALINEACION_TOLERANCIA,
        "reglas": {
            "buy": "POCs alineados + precio > POC promedio",
            "sell": "POCs alineados + precio < POC promedio"
        }
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
