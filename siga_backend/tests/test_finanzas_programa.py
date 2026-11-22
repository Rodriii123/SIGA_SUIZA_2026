"""Pruebas de Finanzas sin Base de datos, sin .env y sin red.

Valida que la carrera mostrada en listados, pagos y comprobantes se resuelva
desde la tabla programas_estudio y no desde IDs o nombres fijos en el código.
"""

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "siga_backend" / "modules" / "mod-gestion-academica"
ROUTES = BACKEND / "routes.py"
TESORERIA = BACKEND / "tesoreria_routes.py"
FINANZAS = ROOT / "siga_frontend" / "src" / "modules" / "finances"
PROGRAMAS_JS = ROOT / "siga_frontend" / "src" / "core" / "api" / "programas.js"

NOMBRES_FIJOS = ("mecatrónica", "mecatronica", "desarrollo de sistemas")


def _sin_tildes(texto):
    return texto.casefold().replace("ó", "o").replace("á", "a").replace("é", "e").replace("í", "i").replace("ú", "u")


def _funcion(arbol, nombre):
    return next(
        n for n in ast.walk(arbol)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre
    )


def _codigo_funcion(nodo, codigo):
    return ast.get_source_segment(codigo, nodo) or ""


class FinanzasProgramaRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.codigo_routes = ROUTES.read_text(encoding="utf-8")
        cls.codigo_tesoreria = TESORERIA.read_text(encoding="utf-8")
        cls.arbol_routes = ast.parse(cls.codigo_routes)
        cls.arbol_tesoreria = ast.parse(cls.codigo_tesoreria)
        cls.archivos_finanzas = {
            ruta.name: ruta.read_text(encoding="utf-8")
            for ruta in FINANZAS.rglob("*") if ruta.is_file()
        }

    def test_listado_estudiantes_devuelve_nombre_y_codigo_del_catalogo(self):
        obtener = _funcion(self.arbol_routes, "obtener_estudiantes")
        cuerpo = _codigo_funcion(obtener, self.codigo_routes)

        self.assertIn("SELECT id, nombre, codigo FROM programas_estudio", cuerpo)
        self.assertIn('"programa_nombre":', cuerpo)
        self.assertIn('"programa_codigo":', cuerpo)
        self.assertIn('programas.get(r.programa_id', cuerpo)

    def test_endpoints_de_estudiante_adjuntan_carrera_oficial(self):
        adjuntar = _funcion(self.arbol_routes, "_adjuntar_programa_estudiante")
        cuerpo = _codigo_funcion(adjuntar, self.codigo_routes)

        self.assertIn("SELECT nombre, codigo FROM programas_estudio WHERE id = :pid", cuerpo)
        self.assertIn("estudiante.programa_nombre =", cuerpo)
        self.assertIn("estudiante.programa_codigo =", cuerpo)

        llamadas = [
            n for n in ast.walk(self.arbol_routes)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_adjuntar_programa_estudiante"
        ]
        # foto alta/baja, crear, actualizar pago, obtener y actualizar estudiante.
        self.assertGreaterEqual(len(llamadas), 6)

    def test_comprobantes_usan_carrera_vigente_no_nombre_guardado(self):
        pago_dict = _funcion(self.arbol_tesoreria, "pago_dict")
        self.assertIn("programa", [arg.arg for arg in pago_dict.args.args])

        cuerpo = _codigo_funcion(pago_dict, self.codigo_tesoreria)
        self.assertIn('(programa or {}).get("nombre") or p.carrera_nombre', cuerpo)

        pagos_dict = _funcion(self.arbol_tesoreria, "pagos_dict")
        cuerpo_pagos = _codigo_funcion(pagos_dict, self.codigo_tesoreria)
        self.assertIn("FROM estudiantes e", cuerpo_pagos)
        self.assertIn("JOIN programas_estudio pr ON pr.id = e.programa_id", cuerpo_pagos)

        llamadas_directas = [
            n for n in ast.walk(self.arbol_tesoreria)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "pago_dict"
        ]
        # Solo la serialización centralizada debe invocar pago_dict.
        self.assertEqual(len(llamadas_directas), 1)

    def test_backend_finanzas_sin_nombres_de_carrera_fijos(self):
        for ruta, codigo in ((ROUTES, self.codigo_routes), (TESORERIA, self.codigo_tesoreria)):
            normalizado = _sin_tildes(codigo)
            for nombre in NOMBRES_FIJOS:
                self.assertNotIn(_sin_tildes(nombre), normalizado, f"{ruta.name} contiene {nombre}")

    def test_frontend_finanzas_sin_mapa_de_ids_ni_nombres_fijos(self):
        for nombre, codigo in self.archivos_finanzas.items():
            self.assertNotIn("CAREERS_MAP", codigo, f"{nombre} todavía usa CAREERS_MAP")
            normalizado = _sin_tildes(codigo)
            for fijo in NOMBRES_FIJOS:
                self.assertNotIn(_sin_tildes(fijo), normalizado, f"{nombre} contiene {fijo}")

    def test_pantallas_toman_carrera_del_campo_real_o_del_catalogo(self):
        self.assertIn("nombreProgramaEstudiante", self.archivos_finanzas["FinancesDashboard.jsx"])
        for nombre in (
            "PaymentModal.jsx",
            "StudentPaymentsModal.jsx",
            "AnnualStatementModal.jsx",
            "PublicVerification.jsx",
        ):
            self.assertIn("programa_nombre", self.archivos_finanzas[nombre], f"{nombre} ignora programa_nombre")

        catalogo = PROGRAMAS_JS.read_text(encoding="utf-8")
        self.assertIn("student?.programa_nombre", catalogo)
        self.assertIn("String(p.id) === String(programaId)", catalogo)


if __name__ == "__main__":
    unittest.main()
