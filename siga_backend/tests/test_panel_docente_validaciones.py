"""
Regresiones del Panel Docente que no requieren PostgreSQL local.

Cubre:
- La nómina expone estado de matrícula/curso e incluye pendientes.
- La validación canónica de matrícula calificable rechaza pendientes/retirados.
- POST y PUT de notas ejecutan esa validación (antes solo la hacía POST).
- El endpoint batch también queda cubierto por la misma validación.
"""
import asyncio
import inspect
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import HTTPException
from shared.identity import Identity

from tests.helpers.module_loader import load_module_component


class FakeResult:
    """Resultado mínimo compatible con las llamadas usadas por los endpoints."""

    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar


class FakeDb:
    """DB en memoria: devuelve resultados en el orden en que el endpoint consulta."""

    def __init__(self, results=None):
        self._results = list(results or [])
        self.calls = []

    async def execute(self, statement, params=None):
        self.calls.append((statement, params))
        if self._results:
            return self._results.pop(0)
        return FakeResult()

    def add(self, _event):
        return None

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


IDENTIDAD_DOCENTE = Identity(
    user_id=10,
    roles=["docente"],
    programa_id=1,
    is_superuser=False,
)


async def _identidad_docente(_request, _db):
    return IDENTIDAD_DOCENTE


async def _sin_validar_cierre(_db, _unidad_id, _periodo_id, _codigo):
    return None


class PanelDocenteValidacionesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluacion = load_module_component("mod-evaluacion", "routes")
        cls.schemas = sys.modules["schemas"]

        # El entorno local no trae email-validator; el schema de gestión solo lo
        # necesita para construir EmailStr. Se simula sin tocar el proyecto.
        email_validator = ModuleType("email_validator")
        email_validator.__version__ = "2.0.0"
        sys.modules.setdefault("email_validator", email_validator)
        with patch("pydantic.networks.version", return_value="2.0.0"), patch(
            "fastapi.dependencies.utils.ensure_multipart_is_installed",
            return_value=None,
        ):
            cls.gestion = load_module_component("mod-gestion-academica", "routes")

    def test_nomina_incluye_pendientes_y_expone_estados(self):
        filas = [
            (
                SimpleNamespace(id=100, nombres="Ana", apellidos="Pérez"),
                5,
                "confirmada",
                80,
                "cursando",
            ),
            (
                SimpleNamespace(id=101, nombres="Luis", apellidos="Ruiz"),
                6,
                "pendiente",
                81,
                "cursando",
            ),
        ]
        db = FakeDb([FakeResult(rows=filas)])

        class FakeEstudianteResponse:
            @staticmethod
            def model_validate(est):
                return SimpleNamespace(
                    model_dump=lambda: {
                        "id": est.id,
                        "nombres": est.nombres,
                        "apellidos": est.apellidos,
                    }
                )

        with patch.object(self.gestion, "EstudianteResponse", FakeEstudianteResponse):
            respuesta = asyncio.run(
                self.gestion.obtener_estudiantes_por_unidad(101, 1, db)
            )

        self.assertEqual(len(respuesta), 2, "La nómina no debe ocultar pendientes")
        por_id = {fila["id"]: fila for fila in respuesta}
        self.assertEqual(por_id[100]["estado_matricula"], "confirmada")
        self.assertEqual(por_id[100]["matricula_detalle_id"], 80)
        self.assertEqual(por_id[101]["estado_matricula"], "pendiente")
        self.assertEqual(por_id[101]["estado_curso"], "cursando")

        sql = str(db.calls[0][0])
        self.assertIn("estado_matricula", sql)
        self.assertIn("estado_curso", sql)
        self.assertNotIn("estado_matricula = 'confirmada'", sql)

    def test_matricula_confirmada_y_no_retirada_es_calificable(self):
        db = FakeDb([FakeResult(rows=[(101, "cursando", 100, 1, "confirmada")])])
        fila = asyncio.run(
            self.evaluacion._validar_matricula_calificable_para_nota(
                db,
                80,
                unidad_id=101,
                periodo_id=1,
                estudiante_id=100,
            )
        )
        self.assertEqual(fila[4], "confirmada")

    def test_matricula_pendiente_no_es_calificable(self):
        db = FakeDb([FakeResult(rows=[(101, "cursando", 100, 1, "pendiente")])])
        with self.assertRaises(HTTPException) as contexto:
            asyncio.run(
                self.evaluacion._validar_matricula_calificable_para_nota(db, 80)
            )
        self.assertEqual(contexto.exception.status_code, 409)
        self.assertIn("pendiente", contexto.exception.detail)

    def test_detalle_retirado_no_es_calificable(self):
        db = FakeDb([FakeResult(rows=[(101, "retirado", 100, 1, "confirmada")])])
        with self.assertRaises(HTTPException) as contexto:
            asyncio.run(
                self.evaluacion._validar_matricula_calificable_para_nota(db, 81)
            )
        self.assertEqual(contexto.exception.status_code, 409)
        self.assertIn("retirado", contexto.exception.detail)

    def test_detalle_de_otra_unidad_o_periodo_se_rechaza(self):
        db = FakeDb([FakeResult(rows=[(999, "cursando", 100, 99, "confirmada")])])
        with self.assertRaises(HTTPException) as contexto:
            asyncio.run(
                self.evaluacion._validar_matricula_calificable_para_nota(
                    db, 80, unidad_id=101, periodo_id=1
                )
            )
        self.assertEqual(contexto.exception.status_code, 404)

    def test_se_requiere_detalle_de_matricula(self):
        with self.assertRaises(HTTPException) as contexto:
            asyncio.run(
                self.evaluacion._validar_matricula_calificable_para_nota(FakeDb(), None)
            )
        self.assertEqual(contexto.exception.status_code, 422)

    def test_post_de_notas_rechaza_matricula_pendiente(self):
        datos = self.schemas.RegistroEvaluacionCreate(
            matricula_detalle_id=80,
            estudiante_id=100,
            unidad_didactica_id=101,
            periodo_id=1,
            nota_final=18,
        )
        db = FakeDb([
            FakeResult(rows=[(1, 10)]),  # carga lectiva del docente
            FakeResult(rows=[("2027-I", "matricula_abierta")]),  # periodo
            FakeResult(rows=[(101, "cursando", 100, 1, "pendiente")]),  # matrícula
        ])
        request = SimpleNamespace(headers={})
        parches = [
            patch.object(self.evaluacion, "get_identity", new=_identidad_docente),
            patch.object(self.evaluacion, "es_superadmin", return_value=False),
            patch.object(
                self.evaluacion,
                "_validar_cierre_y_fecha_limite",
                new=_sin_validar_cierre,
            ),
        ]
        for parche in parches:
            parche.start()
        try:
            with self.assertRaises(HTTPException) as contexto:
                asyncio.run(self.evaluacion.crear_registro(datos, request, db))
        finally:
            for parche in reversed(parches):
                parche.stop()

        self.assertEqual(contexto.exception.status_code, 409)
        self.assertIn("pendiente", contexto.exception.detail)

    def test_put_de_notas_rechaza_matricula_pendiente(self):
        registro = SimpleNamespace(
            id=1,
            matricula_detalle_id=80,
            estudiante_id=100,
            unidad_didactica_id=101,
            periodo_id=1,
            estado="cursando",
            nota_final=15,
            nota_c1=None,
            nota_c2=None,
            nota_c3=None,
        )
        datos = self.schemas.RegistroEvaluacionUpdate(nota_final=18)
        db = FakeDb([
            FakeResult(scalar=registro),  # registro existente
            FakeResult(rows=[(1, 10)]),  # carga lectiva
            FakeResult(rows=[("2027-I", "matricula_abierta")]),  # periodo
            FakeResult(rows=[(101, "cursando", 100, 1, "pendiente")]),  # matrícula
        ])
        request = SimpleNamespace(headers={})
        parches = [
            patch.object(self.evaluacion, "get_identity", new=_identidad_docente),
            patch.object(self.evaluacion, "es_superadmin", return_value=False),
            patch.object(
                self.evaluacion,
                "_validar_cierre_y_fecha_limite",
                new=_sin_validar_cierre,
            ),
        ]
        for parche in parches:
            parche.start()
        try:
            with self.assertRaises(HTTPException) as contexto:
                asyncio.run(self.evaluacion.actualizar_notas(1, datos, request, db))
        finally:
            for parche in reversed(parches):
                parche.stop()

        self.assertEqual(contexto.exception.status_code, 409)
        self.assertIn("pendiente", contexto.exception.detail)

    def test_los_tres_caminos_de_escritura_usan_la_misma_validacion(self):
        for nombre in ("crear_registro", "actualizar_notas", "guardar_registros_batch"):
            funcion = getattr(self.evaluacion, nombre)
            self.assertIn(
                "_validar_matricula_calificable_para_nota",
                inspect.getsource(funcion),
                f"{nombre} no valida la matrícula antes de escribir la nota",
            )


if __name__ == "__main__":
    unittest.main()
