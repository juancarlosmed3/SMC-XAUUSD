from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

from smc_utils import (
    ALINEACION_TOLERANCIA,
    poc_multi_tf_alineado,
    poc_promedio,
    poc_rango,
    resultado,
)

app = FastAPI(title="API de Validación SMC - XAU/USD", version="1.0")

# --- Simulación de POCs alineados (en producción, vendrían de tu sistema o API externa) ---
# En scalping, usamos timeframe pequeño: 5m, 15m, 1h
POC_REFERENCIA = {
    "5m": 2635.0,
    "15m": 2634.8,
    "1h": 2635.2
}

def validar_senal_smc(
    direccion: str,
    precio_actual: float,
    pocs: dict  # ej: {"5m": 2635, "15m": 2634.8, "1h": 2635.2}
) -> dict:
    """Valida señal según estrategia SMC Scalping"""
    if not poc_multi_tf_alineado(pocs):
        return resultado(
            False,
            "POCs no alineados (rango excede tolerancia)",
            rango_pocs=poc_rango(pocs),
        )

    promedio = poc_promedio(pocs)
    direccion = direccion.upper()

    if direccion == "BUY":
        if precio_actual > promedio:
            return resultado(True, "✅ BUY válida: POCs alineados + precio > POC")
        return resultado(False, "❌ BUY inválida: precio NO supera POC")

    if direccion == "SELL":
        if precio_actual < promedio:
            return resultado(True, "✅ SELL válida: POCs alineados + precio < POC")
        return resultado(False, "❌ SELL inválida: precio NO está bajo POC")

    return resultado(False, "Dirección no reconocida (usa BUY/SELL)")

# --- Modelos de datos ---
class SenalSMC(BaseModel):
    activo: str
    timeframe: str
    direccion: str  # "BUY" o "SELL"
    precio_actual: float
    pocs: dict  # ej: {"5m": 2635.0, "15m": 2634.8, "1h": 2635.2}

# --- Endpoints ---
@app.get("/")
def home():
    return {"mensaje": "API SMC Scalping activa - XAU/USD"}

@app.post("/validar_senal")
def validar_senal(senal: SenalSMC):
    if senal.activo.upper() != "XAUUSD":
        raise HTTPException(status_code=400, detail="Solo se acepta XAUUSD")
    
    resultado = validar_senal_smc(
        direccion=senal.direccion,
        precio_actual=senal.precio_actual,
        pocs=senal.pocs
    )
    
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