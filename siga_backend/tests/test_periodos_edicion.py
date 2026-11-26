"""Pruebas de integración de la edición segura de periodos lectivos.

Se ejecutan únicamente contra ``siga_test`` (conftest.py aborta cualquier otra BD)
y se omiten automáticamente cuando no hay SECRET_KEY o PostgreSQL de pruebas.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.module_loader import load_module_component
from tests.helpers.jwt_helper import auth_headers


@pytest_asyncio.fixture
async def app_periodos():
    routes_mod = load_module_component("mod-programas-estudio", "routes")
    app = FastAPI()
    app.include_router(routes_mod.router)
    return app, routes_mod


@pytest_asyncio.fixture
async def client_periodos(app_periodos):
    app, _ = app_periodos
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test-periodos") as client:
        yield client


@pytest_asyncio.fixture
async def periodos_edicion(db_session: AsyncSession):
    """Crea dos periodos de prueba; el primero tiene una relación real (horario)."""
    await db_session.execute(text(
        "ALTER TABLE periodos_academicos ADD COLUMN IF NOT EXISTS nombre VARCHAR(120)"
    ))
    await db_session.execute(text("""
        INSERT INTO programas_estudio (id, nombre, codigo, creditos_totales, duracion_periodos, modalidad, estado, created_at, updated_at)
        VALUES (501, 'Programa Prueba Periodos', 'PP-501', 120, 6, 'presencial', 'activo', NOW(), NOW())
        ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre;
    """))
    await db_session.execute(text("""
        INSERT INTO periodos_academicos
            (id, codigo, nombre, fecha_inicio, fecha_fin, fecha_fin_matricula_regular,
             fecha_fin_matricula_extemporanea, estado, created_at, updated_at)
        VALUES
            (501, '2027-I', 'Primer Semestre 2027', '2027-01-10', '2027-06-20',
             '2027-02-20', '2027-03-05', 'en_curso', NOW(), NOW()),
            (502, '2027-II', 'Segundo Semestre 2027', '2027-08-03', '2027-12-18',
             '2027-09-03', '2027-09-18', 'planificacion', NOW(), NOW())
        ON CONFLICT (id) DO UPDATE SET
            codigo = EXCLUDED.codigo,
            nombre = EXCLUDED.nombre,
            fecha_inicio = EXCLUDED.fecha_inicio,
            fecha_fin = EXCLUDED.fecha_fin,
            fecha_fin_matricula_regular = EXCLUDED.fecha_fin_matricula_regular,
            fecha_fin_matricula_extemporanea = EXCLUDED.fecha_fin_matricula_extemporanea,
            estado = EXCLUDED.estado;
    """))
    await db_session.execute(text("""
        INSERT INTO horarios_periodo (id, periodo_id, programa_id, estado, archivo_excel_url, created_at, updated_at)
        VALUES (501, 501, 501, 'borrador', 'http://test/horario.xlsx', NOW(), NOW())
        ON CONFLICT (id) DO UPDATE SET periodo_id = 501;
    """))
    await db_session.commit()
    return {"con_relaciones": 501, "sin_relaciones": 502}


def payload_periodo(**cambios):
    datos = {
        "codigo": "2027-I",
        "fecha_inicio": "2027-01-10T00:00:00",
        "fecha_fin": "2027-06-20T00:00:00",
        "fecha_fin_matricula_regular": "2027-02-20T00:00:00",
        "fecha_fin_matricula_extemporanea": "2027-03-05T00:00:00",
        "estado": "en_curso",
    }
    datos.update(cambios)
    return datos


@pytest.mark.asyncio
async def test_editar_periodo_persiste_y_se_ve_tras_recargar(client_periodos, db_session, periodos_edicion):
    cambios = payload_periodo(
        fecha_fin="2027-06-30T00:00:00",
        estado="matricula_abierta",
    )
    respuesta = await client_periodos.put("/periodos/501", headers=auth_headers(1), json=cambios)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "2027-I"
    assert cuerpo["nombre"] == "2027-I"  # columna legada alineada al código
    assert cuerpo["estado"] == "matricula_abierta"
    assert cuerpo["fecha_fin"].startswith("2027-06-30")
    assert cuerpo["relaciones"]["horarios"] == 1

    # La recarga del listado (sin token, como hace el frontend) devuelve el dato guardado.
    listado = await client_periodos.get("/periodos")
    assert listado.status_code == 200
    periodo = next(p for p in listado.json() if p["id"] == 501)
    assert periodo["nombre"] == "2027-I"
    assert periodo["estado"] == "matricula_abierta"
    assert periodo["relaciones"]["total"] >= 1

    fila = (await db_session.execute(text(
        "SELECT nombre, estado FROM periodos_academicos WHERE id = 501"
    ))).one()
    assert fila == ("2027-I", "matricula_abierta")


@pytest.mark.asyncio
async def test_editar_periodo_valida_duplicados_fechas_y_estado(client_periodos, periodos_edicion):
    # Código duplicado.
    respuesta = await client_periodos.put(
        "/periodos/502", headers=auth_headers(1), json=payload_periodo(codigo="2027-I")
    )
    assert respuesta.status_code == 409
    assert "Ya existe un periodo" in respuesta.json()["detail"]

    # Fechas invertidas.
    respuesta = await client_periodos.put(
        "/periodos/502", headers=auth_headers(1), json=payload_periodo(fecha_fin="2027-01-01T00:00:00")
    )
    assert respuesta.status_code == 422

    # Matrícula extemporánea anterior a la regular.
    respuesta = await client_periodos.put(
        "/periodos/502",
        headers=auth_headers(1),
        json=payload_periodo(fecha_fin_matricula_extemporanea="2027-02-01T00:00:00"),
    )
    assert respuesta.status_code == 422

    # Estado desconocido.
    respuesta = await client_periodos.put(
        "/periodos/502", headers=auth_headers(1), json=payload_periodo(estado="inventado")
    )
    assert respuesta.status_code == 422

    # Ninguna petición inválida modificó el periodo 502.
    listado = await client_periodos.get("/periodos")
    periodo = next(p for p in listado.json() if p["id"] == 502)
    assert periodo["codigo"] == "2027-II"
    assert periodo["estado"] == "planificacion"


@pytest.mark.asyncio
async def test_edicion_exige_identidad_y_roles(client_periodos, periodos_edicion):
    cambios = payload_periodo()

    sin_token = await client_periodos.put("/periodos/502", json=cambios)
    assert sin_token.status_code == 401

    docente = await client_periodos.put("/periodos/502", headers=auth_headers(10), json=cambios)
    assert docente.status_code == 403

    coordinador = await client_periodos.put(
        "/periodos/502", headers=auth_headers(2), json=payload_periodo(codigo="2027-II")
    )
    assert coordinador.status_code == 200


@pytest.mark.asyncio
async def test_no_se_cambia_codigo_cuando_hay_relaciones(client_periodos, periodos_edicion):
    respuesta = await client_periodos.put(
        "/periodos/501", headers=auth_headers(1), json=payload_periodo(codigo="2027-IB")
    )
    assert respuesta.status_code == 409
    assert "No se puede cambiar el código" in respuesta.json()["detail"]

    # Sí se permite editar fechas/estado sin tocar el código.
    permitido = await client_periodos.put(
        "/periodos/501",
        headers=auth_headers(1),
        json=payload_periodo(estado="planificacion"),
    )
    assert permitido.status_code == 200
    assert permitido.json()["codigo"] == "2027-I"

    # Un periodo sin relaciones sí puede cambiar de código.
    libre = await client_periodos.put(
        "/periodos/502",
        headers=auth_headers(1),
        json=payload_periodo(codigo="2027-IIB"),
    )
    assert libre.status_code == 200
    assert libre.json()["codigo"] == "2027-IIB"
    assert libre.json()["nombre"] == "2027-IIB"


@pytest.mark.asyncio
async def test_crear_periodo_no_acepta_nombre_del_formulario(client_periodos, db_session, periodos_edicion):
    respuesta = await client_periodos.post(
        "/periodos",
        headers=auth_headers(1),
        json=payload_periodo(codigo="2027-III", nombre="Campo que no debe usarse"),
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "2027-III"
    assert cuerpo["nombre"] == "2027-III"

    fila = (await db_session.execute(text(
        "SELECT nombre FROM periodos_academicos WHERE codigo = '2027-III'"
    ))).scalar_one()
    assert fila == "2027-III"
