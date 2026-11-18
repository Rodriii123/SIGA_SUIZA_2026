"""Pruebas unitarias para el esquema de Trámites y Casuísticas (sin BD).

Ejecutar desde modules/mod-gestion-academica:
    python -m unittest test_tramites_schema -v
"""
import unittest

from pydantic import ValidationError

from schemas import SolicitudTramiteCreate, SolicitudTramiteResponse


class TestTramitesSchema(unittest.TestCase):

    def test_response_tolera_estado_y_fecha_nulos(self):
        """Los registros históricos con NULL no deben romper la lista completa."""
        tramite = SolicitudTramiteResponse(
            id=7,
            estudiante_id=1,
            tipo_tramite="Constancia de Estudios",
            estado=None,
            fecha_solicitud=None,
        )

        self.assertIsNone(tramite.estado)
        self.assertIsNone(tramite.fecha_solicitud)

    def test_create_recorta_el_tipo_de_tramite(self):
        tramite = SolicitudTramiteCreate(
            estudiante_id=1,
            tipo_tramite="  Reserva de Matrícula  ",
        )

        self.assertEqual(tramite.tipo_tramite, "Reserva de Matrícula")

    def test_create_rechaza_tipo_de_tramite_vacio(self):
        with self.assertRaises(ValidationError):
            SolicitudTramiteCreate(estudiante_id=1, tipo_tramite="   ")

    def test_response_mantiene_observaciones_opcionales(self):
        tramite = SolicitudTramiteResponse(
            id=1,
            estudiante_id=1,
            tipo_tramite="Certificado de Estudios",
            estado="pendiente",
            fecha_solicitud="2026-11-18",
            observaciones=None,
        )

        self.assertIsNone(tramite.observaciones)


if __name__ == "__main__":
    unittest.main()
