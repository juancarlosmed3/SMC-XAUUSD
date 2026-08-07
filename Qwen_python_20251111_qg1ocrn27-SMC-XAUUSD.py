import os
import secrets
from typing import Dict

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="API de Validación SMC - XAU/USD", version="1.0")

API_KEY = os.environ.get("SMC_API_KEY")
TIMEFRAMES_VALIDOS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}
MAX_POCS = 20


def verificar_api_key(x_api_key: str = Header(default="")) -> None:
    """Exige una API key cuando SMC_API_KEY está configurada."""
    if API_KEY and not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="API key inválida")

# --- Simulación de POCs alineados (en producción, vendrían de tu sistema o API externa) ---
# En scalping, usamos timeframe pequeño: 5m, 15m, 1h
POC_REFERENCIA = {
    "5m": 2635.0,
    "15m": 2634.8,
    "1h": 2635.2
}

# Alineación permitida: ±$2.0
ALINEACION_TOLERANCIA = 2.0

def poc_multi_tf_alineado(pocs_recibidos: Dict[str, float]) -> bool:
    """Verifica si los POCs están alineados dentro de tolerancia"""
    valores = list(pocs_recibidos.values())
    rango = max(valores) - min(valores)
    return rango <= ALINEACION_TOLERANCIA

def validar_senal_smc(
    direccion: str,
    precio_actual: float,
    pocs: Dict[str, float]  # ej: {"5m": 2635, "15m": 2634.8, "1h": 2635.2}
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
    activo: str = Field(max_length=16)
    timeframe: str = Field(max_length=8)
    direccion: str = Field(max_length=8)  # "BUY" o "SELL"
    precio_actual: float = Field(gt=0, lt=1_000_000)
    pocs: Dict[str, float] = Field(min_length=1, max_length=MAX_POCS)

    @field_validator("direccion")
    @classmethod
    def _direccion_valida(cls, v: str) -> str:
        if v.upper() not in {"BUY", "SELL"}:
            raise ValueError("direccion debe ser BUY o SELL")
        return v.upper()

    @field_validator("timeframe")
    @classmethod
    def _timeframe_valido(cls, v: str) -> str:
        if v not in TIMEFRAMES_VALIDOS:
            raise ValueError(f"timeframe debe ser uno de {sorted(TIMEFRAMES_VALIDOS)}")
        return v

    @field_validator("pocs")
    @classmethod
    def _pocs_validos(cls, v: Dict[str, float]) -> Dict[str, float]:
        for tf, valor in v.items():
            if tf not in TIMEFRAMES_VALIDOS:
                raise ValueError(f"timeframe de POC inválido: {tf}")
            if not 0 < valor < 1_000_000:
                raise ValueError(f"valor de POC fuera de rango: {valor}")
        return v

# --- Endpoints ---
@app.get("/")
def home():
    return {"mensaje": "API SMC Scalping activa - XAU/USD"}

@app.post("/validar_senal", dependencies=[Depends(verificar_api_key)])
def validar_senal(senal: SenalSMC):
    if senal.activo.upper() != "XAUUSD":
        raise HTTPException(status_code=400, detail="Solo se acepta XAUUSD")
    
    resultado = validar_senal_smc(
        direccion=senal.direccion,
        precio_actual=senal.precio_actual,
        pocs=senal.pocs
    )
    
    return {
        "senal_recibida": senal.model_dump(),
        "resultado": resultado
    }

@app.get("/estado_xau", dependencies=[Depends(verificar_api_key)])
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