"""Reglas puras de validación de periodos lectivos.

Este módulo no depende de FastAPI ni de SQLAlchemy para que pueda probarse
de forma aislada; las rutas traducen ``ValidacionPeriodoError`` a HTTP 422.
"""
from dataclasses import dataclass
import re
from typing import Any, Dict


ESTADOS_PERIODO_VALIDOS = {
    "planificacion", "matricula_abierta", "en_curso", "historico", "cerrado"
}
ROLES_GESTION_PERIODOS = {"secretaria_academica", "coordinador_programa"}


@dataclass
class ValidacionPeriodoError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


def normalizar_codigo_periodo(codigo: Any) -> str:
    return str(codigo or "").strip().upper()


def limpiar_fechas_periodo(datos: Dict[str, Any]) -> Dict[str, Any]:
    """Convierte fechas con timezone a naive para columnas TIMESTAMP."""
    limpios = dict(datos)
    for clave in (
        "fecha_inicio", "fecha_fin",
        "fecha_fin_matricula_regular", "fecha_fin_matricula_extemporanea"
    ):
        valor = limpios.get(clave)
        if valor is not None and getattr(valor, "tzinfo", None):
            limpios[clave] = valor.replace(tzinfo=None)
    return limpios


def validar_datos_periodo(datos: Dict[str, Any]) -> None:
    """Valida códigos, fechas y estado. Levanta ValidacionPeriodoError si falla."""
    codigo = normalizar_codigo_periodo(datos.get("codigo"))
    if not codigo or len(codigo) > 20:
        raise ValidacionPeriodoError("El código del periodo es obligatorio (máximo 20 caracteres)")
    if not re.fullmatch(r"[A-Z0-9-]{3,20}", codigo):
        raise ValidacionPeriodoError(
            "El código solo puede contener letras, números y guiones (mínimo 3 caracteres)"
        )

    inicio = datos.get("fecha_inicio")
    fin = datos.get("fecha_fin")
    regular = datos.get("fecha_fin_matricula_regular")
    extemporanea = datos.get("fecha_fin_matricula_extemporanea")
    if not all([inicio, fin, regular, extemporanea]):
        raise ValidacionPeriodoError("Todas las fechas del cronograma son obligatorias")
    if inicio >= fin:
        raise ValidacionPeriodoError("La fecha de fin debe ser posterior a la fecha de inicio")
    if regular < inicio or regular > fin:
        raise ValidacionPeriodoError("El cierre de matrícula regular debe estar dentro del periodo lectivo")
    if extemporanea < regular:
        raise ValidacionPeriodoError(
            "El cierre de matrícula extemporánea no puede ser anterior al cierre regular"
        )
    if extemporanea > fin:
        raise ValidacionPeriodoError("El cierre de matrícula extemporánea no puede superar la fecha de fin")

    estado = str(datos.get("estado") or "").lower()
    if estado not in ESTADOS_PERIODO_VALIDOS:
        raise ValidacionPeriodoError(f"Estado de periodo no válido: {estado or '(vacío)'}")
