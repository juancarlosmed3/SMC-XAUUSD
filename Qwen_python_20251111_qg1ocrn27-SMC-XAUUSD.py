from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

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

def poc_multi_tf_alineado(pocs_recibidos: dict) -> bool:
    """Verifica si los POCs están alineados dentro de tolerancia"""
    valores = list(pocs_recibidos.values())
    rango = max(valores) - min(valores)
    return rango <= ALINEACION_TOLERANCIA

def validar_senal_smc(
    direccion: str,
    precio_actual: float,
    pocs: dict  # ej: {"5m": 2635, "15m": 2634.8, "1h": 2635.2}
) -> dict:
    """Valida señal según estrategia SMC Scalping"""
    alineado = poc_multi_tf_alineado(pocs)
    
    if not alineado:
        return {
            "valida": False,
            "motivo": "POCs no alineados (rango excede tolerancia)",
            "rango_pocs": max(pocs.values()) - min(pocs.values())
        }

    # POC promedio para comparar
    poc_promedio = sum(pocs.values()) / len(pocs)

    if direccion.upper() == "BUY":
        if precio_actual > poc_promedio:
            return {"valida": True, "motivo": "✅ BUY válida: POCs alineados + precio > POC"}
        else:
            return {"valida": False, "motivo": "❌ BUY inválida: precio NO supera POC"}
    
    elif direccion.upper() == "SELL":
        if precio_actual < poc_promedio:
            return {"valida": True, "motivo": "✅ SELL válida: POCs alineados + precio < POC"}
        else:
            return {"valida": False, "motivo": "❌ SELL inválida: precio NO está bajo POC"}
    
    else:
        return {"valida": False, "motivo": "Dirección no reconocida (usa BUY/SELL)"}

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