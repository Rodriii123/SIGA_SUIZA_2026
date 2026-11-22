"""Pruebas de Admisión y Matrícula sin BD, sin .env y sin red.

Las funciones se extraen por AST para no importar módulos que crean engine o
leen configuración. Verifican que la carrera siempre se resuelva desde el
catálogo oficial y que no queden ID fijos ni "primera carrera disponible".
"""

import ast
import json
import pathlib
import sys
import types
import unicodedata
import unittest
from typing import List, Optional
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "siga_backend" / "modules" / "mod-gestion-academica"
ROUTES = BACKEND / "routes.py"
MATRICULA = BACKEND / "matricula_routes.py"
ADMISION = ROOT / "siga_backend" / "modules" / "mod-admision" / "main.py"
FRONTEND = ROOT / "siga_frontend" / "src" / "modules" / "enrollment"
STUDENT_MASTER = ROOT / "siga_frontend" / "src" / "modules" / "students" / "StudentMaster.jsx"

CATALOGO = [
    {"id": 6, "nombre": "Mecatrónica Automotriz"},
    {"id": 15, "nombre": "Desarrollo de Sistemas de Información"},
]


def _nodo(arbol, nombre):
    return next(
        n for n in ast.walk(arbol)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre
    )


def _fuente(arbol, nombre, codigo):
    return ast.get_source_segment(codigo, _nodo(arbol, nombre)) or ""


class PandasFalso(types.ModuleType):
    @staticmethod
    def isna(valor):
        return valor is None


class AdmissionMatriculaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.codigo_routes = ROUTES.read_text(encoding="utf-8")
        cls.codigo_matricula = MATRICULA.read_text(encoding="utf-8")
        cls.arbol_routes = ast.parse(cls.codigo_routes)
        cls.arbol_matricula = ast.parse(cls.codigo_matricula)

        helpers_routes = [
            _nodo(cls.arbol_routes, "_normalizar_programa"),
            _nodo(cls.arbol_routes, "_resolver_programa_id"),
        ]
        cls.espacio_routes = {"unicodedata": unicodedata}
        exec(
            compile(ast.Module(body=helpers_routes, type_ignores=[]), str(ROUTES), "exec"),
            cls.espacio_routes,
        )

        nombres_matricula = {
            "_MAP_COLUMNAS", "_normaliza_header", "_resolver_columnas",
            "_limpiar", "_normalizar_programa", "_resolver_programa_id",
            "parse_json_ingresantes",
        }
        nodos_matricula = [
            n for n in cls.arbol_matricula.body
            if (isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_MAP_COLUMNAS" for t in n.targets))
            or (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in nombres_matricula)
        ]
        cls.espacio_matricula = {
            "json": json,
            "pd": PandasFalso("pandas"),
            "unicodedata": unicodedata,
            "List": List,
            "Optional": Optional,
        }
        exec(
            compile(ast.Module(body=nodos_matricula, type_ignores=[]), str(MATRICULA), "exec"),
            cls.espacio_matricula,
        )

        cls.codigo_admision = ADMISION.read_text(encoding="utf-8")
        arbol_admision = ast.parse(cls.codigo_admision)
        get_admitidos = _nodo(arbol_admision, "get_admitidos")
        internos = [
            n for n in ast.walk(get_admitidos)
            if isinstance(n, ast.FunctionDef) and n.name in {"normalizar", "resolver_programa"}
        ]
        cls.espacio_admision = {"unicodedata": unicodedata}
        exec(
            compile(ast.Module(body=internos, type_ignores=[]), str(ADMISION), "exec"),
            cls.espacio_admision,
        )

    # ---------------------- resolvedores reales ----------------------

    def test_ingesta_resuelve_dsi_y_rechaza_id_conflictivo(self):
        resolver = self.espacio_routes["_resolver_programa_id"]
        self.assertEqual(resolver(None, "Desarrollo de Sistemas de Información", CATALOGO), 15)
        self.assertEqual(resolver(15, None, CATALOGO), 15)
        self.assertIsNone(resolver(6, "Desarrollo de Sistemas de Información", CATALOGO))
        self.assertIsNone(resolver(99, None, CATALOGO))

    def test_admision_resuelve_nombre_oficial_sin_adivinar(self):
        resolver = self.espacio_admision["resolver_programa"]
        self.espacio_admision["programas_normalizados"] = [
            (p["id"], self.espacio_admision["normalizar"](p["nombre"])) for p in CATALOGO
        ]
        self.assertEqual(resolver("  desarrollo de sistemas de informacion "), 15)
        self.assertEqual(resolver("Mecatrónica Automotriz"), 6)
        self.assertIsNone(resolver("Medicina"))
        self.assertIsNone(resolver("Automotriz e Industrial"))

    def test_json_de_admision_conserva_el_nombre_de_carrera(self):
        parsear = self.espacio_matricula["parse_json_ingresantes"]
        payload = json.dumps({"admitidos": [{
            "dni": "12345678",
            "nombres": "ANA",
            "apellidos": "PEREZ",
            "PROGRAMA DE   ESTUDIOS": "Desarrollo de Sistemas de Información",
            "correo": "ana@example.com",
        }]}).encode("utf-8")

        registros = parsear(payload)

        self.assertEqual(len(registros), 1)
        self.assertEqual(
            registros[0]["programa_nombre"],
            "Desarrollo de Sistemas de Información",
        )
        self.assertIsNone(registros[0]["programa_id"])

    def test_resolutor_de_matricula_no_acepta_id_equivocado(self):
        resolver = self.espacio_matricula["_resolver_programa_id"]
        self.assertEqual(resolver(None, "Desarrollo de Sistemas de Información", CATALOGO), 15)
        self.assertEqual(resolver("15", None, CATALOGO), 15)
        self.assertIsNone(resolver(6, "Desarrollo de Sistemas de Información", CATALOGO))
        self.assertIsNone(resolver("abc", None, CATALOGO))

    # ---------------------- sin defaults inseguros ----------------------

    def test_ingesta_y_sync_no_tienen_or_1(self):
        ingesta = _fuente(self.arbol_routes, "ingesta_admitidos", self.codigo_routes)
        sync = _fuente(self.arbol_routes, "sincronizar_estudiantes_seccion", self.codigo_routes)
        self.assertIn("_resolver_programa_id(", ingesta)
        self.assertNotIn(" or 1", ingesta)
        self.assertNotIn(" or 1", sync)

    def test_subida_de_ingresantes_valida_contra_catalogo(self):
        subida = _fuente(self.arbol_matricula, "admision_excel", self.codigo_matricula)
        self.assertIn("_catalogo_programas(db)", subida)
        self.assertIn("resolver_programa(reg)", subida)
        self.assertIn("programa_nombre_resuelto", subida)
        self.assertIn("status_code=422", subida)
        self.assertNotIn('reg["programa_id"] or programa_id', subida)
        self.assertNotIn("prog.isdigit()", subida)
        # La matrícula automática sigue existiendo, pero ya no se filtra por un ID elegido a ciegas.
        self.assertIn("estudiante_ids=ids_creados", subida)

    def test_archivos_de_admision_y_matricula_sin_ids_fijos(self):
        for ruta, codigo in (
            (ROUTES, self.codigo_routes),
            (MATRICULA, self.codigo_matricula),
            (ADMISION, self.codigo_admision),
        ):
            self.assertNotIn("programa_id=1", codigo, f"{ruta.name} asigna programa_id=1")
            self.assertNotIn("programa_id = 1", codigo, f"{ruta.name} asigna programa_id = 1")
            self.assertNotIn(" or 1,", codigo, f"{ruta.name} usa 'or 1'")

    # ---------------------- frontend de Admisión/Matrícula ----------------------

    def test_paneles_no_preseleccionan_la_primera_carrera(self):
        for nombre in ("AdmissionPanel.jsx", "DeterminacionPanel.jsx", "RestriccionesPanel.jsx"):
            codigo = (FRONTEND / nombre).read_text(encoding="utf-8")
            self.assertNotIn("[0].id", codigo, f"{nombre} preselecciona la primera carrera")

    def test_matricula_extraordinaria_usa_catalogo_oficial(self):
        codigo = (FRONTEND / "ExtraordinaryEnrollmentModal.jsx").read_text(encoding="utf-8")
        self.assertIn("/api/mod-programas-estudio/programas", codigo)
        self.assertIn("programas.map((p)", codigo)
        self.assertNotIn("currentPrograma === 'ALL' ? '1'", codigo)
        self.assertNotIn('<option value="1">', codigo)

        dashboard = (FRONTEND / "EnrollmentDashboard.jsx").read_text(encoding="utf-8")
        self.assertNotIn("secretaria_prog@siga.edu", dashboard)

    def test_boton_sincronizar_envia_lista_de_admision_a_ingesta(self):
        codigo = STUDENT_MASTER.read_text(encoding="utf-8")
        self.assertIn("/api/mod-admision/admitidos", codigo)
        self.assertIn("/api/mod-gestion-academica/admision/ingesta", codigo)
        self.assertIn("JSON.stringify(admisionData)", codigo)
        self.assertIn("result.estudiantes_creados", codigo)
        self.assertNotIn("secretaria_prog@siga.edu", codigo)


if __name__ == "__main__":
    with patch.dict(sys.modules, {"pandas": PandasFalso("pandas")}):
        unittest.main()
