"""Pruebas del boletín sin Base de datos, sin .env y sin red.

Se extraen las funciones puras de routes.py por AST para no importar el
módulo completo (evita crear el engine de la Base de datos).
"""

import ast
import asyncio
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTES = ROOT / "siga_backend" / "modules" / "mod-gestion-academica" / "routes.py"

FUNCIONES = {
    "_seleccionar_programa_boletin",
    "_obtener_notas_boletin",
    "_obtener_docentes_boletin",
    "_armar_ciclos_boletin",
    "_construir_ciclos_programa",
    "_construir_ciclos",
    "_titulo_ciclo",
    "_numero_ciclo",
    "_nombre_unidad_boletin",
}


class _Mappings:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas

    def first(self):
        return self._filas[0] if self._filas else None


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def mappings(self):
        return _Mappings(self._filas)

    def scalars(self):
        return _Mappings(self._filas)


class _DBFalsa:
    """Simula únicamente db.execute() para las consultas del boletín."""

    def __init__(self, **tablas):
        self.tablas = tablas

    async def execute(self, sentencia, parametros=None):
        sql = " ".join(str(sentencia).split())
        params = parametros or {}

        if "FROM programa_unidades pu" in sql and "JOIN programa_modulos pm" in sql:
            filas = self.tablas.get("nombres_programa", [])
            if params.get("prog_id") is not None:
                filas = [f for f in filas if f.get("programa_id") == params["prog_id"]]
            return _Resultado(filas)
        if "FROM programa_modulos" in sql:
            return _Resultado(self.tablas.get("modulos_programa", []))
        if "FROM programa_unidades u" in sql:
            return _Resultado(self.tablas.get("unidades_programa", []))
        if "FROM programa_unidades" in sql:
            return _Resultado(self.tablas.get("todas_unidades_programa", []))
        if "FROM modulos_plan" in sql:
            return _Resultado(self.tablas.get("modulos_plan", []))
        if "FROM unidades_plan" in sql:
            return _Resultado(self.tablas.get("unidades_plan", []))
        if "FROM evaluacion_registros" in sql:
            return _Resultado(self.tablas.get("evaluaciones", []))
        if "FROM periodos_academicos" in sql:
            return _Resultado(self.tablas.get("periodos", []))
        if "FROM carga_lectiva" in sql:
            filas = self.tablas.get("carga", [])
            if "cl.programa_id" in sql and params.get("prog_id") is not None:
                filas = [f for f in filas if f.get("programa_id") == params["prog_id"]]
            return _Resultado(filas)

        raise AssertionError(f"Consulta inesperada: {sql}")


class BoletinDatosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.codigo = ROUTES.read_text(encoding="utf-8")
        arbol = ast.parse(cls.codigo)
        nodos = [
            n for n in arbol.body
            if (
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name in FUNCIONES
            ) or (
                isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_ROMANOS" for t in n.targets)
            )
        ]
        nombres = {
            n.name for n in nodos
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if nombres != FUNCIONES:
            raise AssertionError(
                f"Faltan funciones del boletín: {FUNCIONES - nombres}"
            )

        cls.sqlalchemy_falso = types.ModuleType("sqlalchemy")
        cls.sqlalchemy_falso.text = lambda sentencia: sentencia
        cls.espacio = {}
        modulo = ast.Module(body=nodos, type_ignores=[])
        with patch.dict(sys.modules, {"sqlalchemy": cls.sqlalchemy_falso}):
            exec(compile(modulo, str(ROUTES), "exec"), cls.espacio)

    def _ejecutar(self, nombre, *args):
        with patch.dict(sys.modules, {"sqlalchemy": self.sqlalchemy_falso}):
            return asyncio.run(self.espacio[nombre](*args))

    def _db_malla(self, **sobrescribir):
        base = {
            "modulos_programa": [
                {"id": 43, "nombre": "Módulo 1: Electrónica", "periodo": 1, "orden": 1}
            ],
            "unidades_programa": [{
                "id": 298, "programa_modulo_id": 43,
                "nombre": "Sistemas Electrónicos del Automóvil",
                "creditos": 4, "horas": 80, "orden": 1,
            }],
            "modulos_plan": [],
            "unidades_plan": [],
            "evaluaciones": [],
            "periodos": [{"id": 1, "codigo": "2026-I"}],
            "carga": [],
        }
        base.update(sobrescribir)
        return _DBFalsa(**base)

    def _evaluacion(self, **sobrescribir):
        fila = {
            "unidad_didactica_id": 298,
            "matricula_unidad_id": 298,
            "nota_c1": None,
            "nota_c2": None,
            "nota_c3": None,
            "nota_final": 15,
            "estado": "aprobado",
            "periodo_id": 1,
        }
        fila.update(sobrescribir)
        return fila

    def test_programa_real_segun_expediente_y_matricula(self):
        seleccionar = self.espacio["_seleccionar_programa_boletin"]
        programas = [
            {"id": 15, "nombre": "Mecatrónica Automotriz", "plan_estudio_id": 8, "creditos_totales": 120},
            {"id": 4, "nombre": "Gestión Administrativa", "plan_estudio_id": None, "creditos_totales": 120},
        ]

        self.assertEqual(seleccionar(15, 4, programas)["id"], 15)
        self.assertEqual(seleccionar(99, 4, programas)["id"], 4)
        self.assertIsNone(seleccionar(99, 98, programas))

    def test_malla_programa_con_nota_15_aunque_ids_coincidan_con_plan(self):
        db = self._db_malla(
            modulos_plan=[{"id": 43, "nombre": "Ciclo 1", "orden": 1}],
            unidades_plan=[{
                "id": 298, "modulo_id": 43,
                "nombre": "Unidad del plan (no debe mostrarse)",
                "codigo": "PLAN-999", "creditos": 99, "horas": 999,
                "tipo": "Plan", "orden": 1,
            }],
            evaluaciones=[self._evaluacion()],
        )

        ciclos, total = self._ejecutar("_construir_ciclos_programa", db, 2315, 15, 1)

        self.assertEqual(total, 1)
        self.assertEqual(ciclos[0]["titulo"], "CICLO I")
        unidad = ciclos[0]["unidades"][0]
        self.assertEqual(unidad["nombre"], "Sistemas Electrónicos del Automóvil")
        self.assertEqual(unidad["nota"], 15)
        self.assertEqual(unidad["estado"], "aprobado")
        self.assertEqual(unidad["creditos"], 4)
        self.assertEqual(unidad["horas"], 80)
        self.assertEqual(unidad["periodo_codigo"], "2026-I")
        self.assertIsNone(unidad["codigo"])
        self.assertIsNone(unidad["tipo"])
        self.assertNotIn("no debe mostrarse", str(ciclos))

    def test_nota_de_otra_malla_no_se_asocia_al_programa(self):
        db = self._db_malla(
            unidades_plan=[{
                "id": 999, "modulo_id": 43, "nombre": "Unidad ajena al programa",
                "creditos": 20, "horas": 100, "orden": 1,
            }],
            evaluaciones=[self._evaluacion(
                unidad_didactica_id=999, matricula_unidad_id=999
            )],
        )

        ciclos, total = self._ejecutar("_construir_ciclos_programa", db, 2315, 15, 1)

        self.assertEqual(total, 1)
        self.assertEqual(ciclos[0]["unidades"][0]["nombre"], "Sistemas Electrónicos del Automóvil")
        self.assertIsNone(ciclos[0]["unidades"][0]["nota"])

    def test_nota_se_recupera_por_unidad_real_de_la_matricula(self):
        db = self._db_malla(
            evaluaciones=[self._evaluacion(
                unidad_didactica_id=555, matricula_unidad_id=298
            )],
        )

        ciclos, total = self._ejecutar("_construir_ciclos_programa", db, 2315, 15, 1)

        self.assertEqual(total, 1)
        self.assertEqual(ciclos[0]["unidades"][0]["nota"], 15)
        self.assertEqual(ciclos[0]["unidades"][0]["creditos"], 4)

    def test_fallback_al_plan_solo_cuando_el_programa_no_tiene_malla(self):
        db = self._db_malla(
            modulos_programa=[],
            unidades_programa=[],
            modulos_plan=[{"id": 43, "nombre": "Ciclo 1", "orden": 1}],
            unidades_plan=[{
                "id": 298, "modulo_id": 43, "nombre": "Unidad histórica del plan",
                "codigo": "PLAN-298", "creditos": 3, "horas": 60,
                "tipo": "Teoría", "orden": 1,
            }],
            evaluaciones=[self._evaluacion()],
        )

        sin_malla, total_sin_malla = self._ejecutar(
            "_construir_ciclos_programa", db, 2315, 15, 1
        )
        self.assertEqual((sin_malla, total_sin_malla), ([], 0))

        ciclos, total = self._ejecutar("_construir_ciclos", db, 2315, 8, 1)
        self.assertEqual(total, 1)
        self.assertEqual(ciclos[0]["unidades"][0]["nombre"], "Unidad histórica del plan")
        self.assertEqual(ciclos[0]["unidades"][0]["nota"], 15)
        self.assertEqual(ciclos[0]["unidades"][0]["codigo"], "PLAN-298")

    def test_nombre_unidad_prefiere_catalogo_del_programa(self):
        db = _DBFalsa(
            nombres_programa=[{
                "id": 298, "programa_id": 15,
                "nombre": "Sistemas Electrónicos del Automóvil",
            }],
            todas_unidades_programa=[{
                "id": 298, "nombre": "Unidad genérica del programa"
            }],
            unidades_plan=[{"id": 298, "nombre": "Unidad del plan"}],
        )

        nombre = self._ejecutar("_nombre_unidad_boletin", db, 298, 15)
        self.assertEqual(nombre, "Sistemas Electrónicos del Automóvil")

        # Si el ID pertenece solo al plan, se usa ese nombre real.
        db_sin_programa = _DBFalsa(unidades_plan=[{"id": 999, "nombre": "Unidad histórica"}])
        self.assertEqual(
            self._ejecutar("_nombre_unidad_boletin", db_sin_programa, 999, 15),
            "Unidad histórica",
        )

    def test_endpoint_usa_malla_del_programa_y_relacion_real(self):
        self.assertIn("programa_id = fila_programa[\"id\"]", self.codigo)
        self.assertIn("_construir_ciclos_programa(", self.codigo)
        self.assertIn("md.unidad_didactica_id AS matricula_unidad_id", self.codigo)
        self.assertIn("FROM programa_unidades u", self.codigo)
        self.assertIn("JOIN programa_modulos pm ON pm.id = pu.programa_modulo_id", self.codigo)
        self.assertIn("nombre_unidad = await _nombre_unidad_boletin(", self.codigo)
        self.assertNotIn('plan_row["plan_nombre"]', self.codigo)
        self.assertNotIn('"programa_nombre": plan_row', self.codigo)


if __name__ == "__main__":
    unittest.main()
