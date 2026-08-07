"""Utilidades compartidas para la validación de señales SMC (XAU/USD)."""

from typing import Any, Dict, Mapping

# Alineación permitida entre POCs: ±$2.0
ALINEACION_TOLERANCIA = 2.0


def poc_rango(pocs: Mapping[str, float]) -> float:
    """Diferencia entre el POC más alto y el más bajo."""
    valores = list(pocs.values())
    return max(valores) - min(valores)


def poc_promedio(pocs: Mapping[str, float]) -> float:
    """Promedio de los POCs recibidos."""
    valores = list(pocs.values())
    return sum(valores) / len(valores)


def poc_multi_tf_alineado(
    pocs: Mapping[str, float], tolerancia: float = ALINEACION_TOLERANCIA
) -> bool:
    """Verifica si los POCs están alineados dentro de tolerancia."""
    return poc_rango(pocs) <= tolerancia


def resultado(valida: bool, motivo: str, **extra: Any) -> Dict[str, Any]:
    """Construye la respuesta estándar de validación."""
    return {"valida": valida, "motivo": motivo, **extra}
