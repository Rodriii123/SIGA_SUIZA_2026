"""Pruebas puras de las reglas de negocio de periodos lectivos.

No requieren PostgreSQL ni FastAPI: se ejecutan con
``python -m unittest tests.test_period_rules`` desde siga_backend y también
son descubiertas por pytest en el entorno de integración.
"""
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "modules" / "mod-programas-estudio" / "period_rules.py"
)
_spec = importlib.util.spec_from_file_location("period_rules_bajo_prueba", MODULE_PATH)
period_rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(period_rules)


def datos_validos():
    inicio = datetime(2027, 1, 10)
    return {
        "codigo": "2027-i",
        "nombre": "Primer Semestre 2027",
        "fecha_inicio": inicio,
        "fecha_fin": inicio + timedelta(days=160),
        "fecha_fin_matricula_regular": inicio + timedelta(days=40),
        "fecha_fin_matricula_extemporanea": inicio + timedelta(days=55),
        "estado": "planificacion",
    }


class PeriodRulesTest(unittest.TestCase):
    def test_datos_validos_no_levantan_error(self):
        period_rules.validar_datos_periodo(datos_validos())

    def test_codigo_obligatorio_y_formato(self):
        for codigo in ("", "  ", None, "AB", "2027/1", "CODIGO-DEMASIADO-LARGO-123"):
            with self.subTest(codigo=codigo):
                datos = datos_validos()
                datos["codigo"] = codigo
                with self.assertRaises(period_rules.ValidacionPeriodoError):
                    period_rules.validar_datos_periodo(datos)

    def test_codigo_se_normaliza_a_mayusculas_y_sin_espacios(self):
        self.assertEqual(period_rules.normalizar_codigo_periodo("  2027-ii "), "2027-II")

    def test_fechas_invertidas_se_rechazan(self):
        datos = datos_validos()
        datos["fecha_fin"] = datos["fecha_inicio"] - timedelta(days=1)
        with self.assertRaisesRegex(period_rules.ValidacionPeriodoError, "posterior"):
            period_rules.validar_datos_periodo(datos)

    def test_cierre_regular_debe_estar_dentro_del_periodo(self):
        datos = datos_validos()
        datos["fecha_fin_matricula_regular"] = datos["fecha_inicio"] - timedelta(days=1)
        with self.assertRaisesRegex(period_rules.ValidacionPeriodoError, "regular"):
            period_rules.validar_datos_periodo(datos)

        datos = datos_validos()
        datos["fecha_fin_matricula_regular"] = datos["fecha_fin"] + timedelta(days=1)
        with self.assertRaisesRegex(period_rules.ValidacionPeriodoError, "regular"):
            period_rules.validar_datos_periodo(datos)

    def test_cierre_extemporanea_coherente(self):
        datos = datos_validos()
        datos["fecha_fin_matricula_extemporanea"] = datos["fecha_fin_matricula_regular"] - timedelta(days=1)
        with self.assertRaisesRegex(period_rules.ValidacionPeriodoError, "extempor"):
            period_rules.validar_datos_periodo(datos)

        datos = datos_validos()
        datos["fecha_fin_matricula_extemporanea"] = datos["fecha_fin"] + timedelta(days=1)
        with self.assertRaisesRegex(period_rules.ValidacionPeriodoError, "fin"):
            period_rules.validar_datos_periodo(datos)

    def test_estado_debe_ser_uno_de_los_permitidos(self):
        datos = datos_validos()
        datos["estado"] = "inventado"
        with self.assertRaisesRegex(period_rules.ValidacionPeriodoError, "Estado"):
            period_rules.validar_datos_periodo(datos)

        datos["estado"] = "EN_CURSO"
        period_rules.validar_datos_periodo(datos)

    def test_fechas_con_timezone_se_convierten_a_naive(self):
        datos = datos_validos()
        datos["fecha_inicio"] = datetime(2027, 1, 10, tzinfo=timezone.utc)
        limpios = period_rules.limpiar_fechas_periodo(datos)
        self.assertIsNone(limpios["fecha_inicio"].tzinfo)
        self.assertEqual(limpios["fecha_inicio"].hour, 0)

    def test_roles_permitidos_no_incluyen_docente(self):
        self.assertIn("secretaria_academica", period_rules.ROLES_GESTION_PERIODOS)
        self.assertIn("coordinador_programa", period_rules.ROLES_GESTION_PERIODOS)
        self.assertNotIn("docente", period_rules.ROLES_GESTION_PERIODOS)


if __name__ == "__main__":
    unittest.main()
