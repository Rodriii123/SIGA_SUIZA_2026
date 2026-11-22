from fastapi import APIRouter, HTTPException, Depends, status, Request, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, text
from sqlalchemy.orm import selectinload
from database import get_db, OutboxEvent
from models import Estudiante, Matricula, MatriculaDetalle
from schemas import EstudianteCreate, EstudianteResponse, EstudianteUpdate, MatriculaCreate, MatriculaResponse, IngestaMasivaRequest
from datetime import datetime
from typing import List, Optional
from pathlib import Path
import uuid
import unicodedata

router = APIRouter()

FOTO_DIR = Path(__file__).resolve().parent / "uploads" / "fotos"
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_FOTO_SIZE = 5 * 1024 * 1024  # 5 MB


def _foto_path_for(filename: str) -> Path:
    """Devuelve la ruta segura de un archivo de foto (previene path traversal)."""
    return FOTO_DIR / Path(filename).name


def _delete_foto(filename: str | None):
    """Elimina una foto del disco de forma best-effort."""
    if not filename:
        return
    file_name = Path(filename).name
    if not file_name:
        return
    try:
        _foto_path_for(file_name).unlink(missing_ok=True)
    except OSError:
        pass


async def _adjuntar_programa_estudiante(db, estudiante):
    """Añade nombre y código oficiales desde programas_estudio, sin IDs fijos."""
    if estudiante is None:
        return estudiante

    if estudiante.programa_id is None:
        estudiante.programa_nombre = None
        estudiante.programa_codigo = None
        return estudiante

    fila = (await db.execute(
        text("SELECT nombre, codigo FROM programas_estudio WHERE id = :pid"),
        {"pid": estudiante.programa_id}
    )).mappings().first()
    estudiante.programa_nombre = fila["nombre"] if fila else None
    estudiante.programa_codigo = fila["codigo"] if fila else None
    return estudiante

@router.get("/fotos/{filename}")
async def obtener_foto(filename: str):
    """Sirve una foto de estudiante guardada en disco."""
    path = _foto_path_for(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    return FileResponse(path, media_type="image/jpeg")

@router.post("/estudiantes/{estudiante_id}/foto", response_model=EstudianteResponse)
async def subir_foto(estudiante_id: int, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Sube o reemplaza la foto de un estudiante y guarda la URL en foto_url."""
    result = await db.execute(select(Estudiante).where(Estudiante.id == estudiante_id))
    db_estudiante = result.scalar_one_or_none()
    if not db_estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Formato de imagen inválido. Use JPG, PNG o WEBP")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    if len(content) > MAX_FOTO_SIZE:
        raise HTTPException(status_code=400, detail="La imagen supera los 5 MB")

    FOTO_DIR.mkdir(parents=True, exist_ok=True)
    ext = ALLOWED_IMAGE_TYPES[file.content_type]
    filename = f"{estudiante_id}_{uuid.uuid4().hex[:12]}{ext}"
    (FOTO_DIR / filename).write_bytes(content)

    if db_estudiante.foto_url:
        _delete_foto(db_estudiante.foto_url)
    db_estudiante.foto_url = f"/api/mod-gestion-academica/fotos/{filename}"

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "gestion_academica.estudiante.foto_actualizada",
        "source": "mod-gestion-academica",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "data": {"id": db_estudiante.id},
        "metadata": {"request_id": request.headers.get("X-Request-ID", "unknown")}
    }
    db.add(OutboxEvent(event_type=event_payload["event_type"], payload=event_payload))
    await db.commit()
    await db.refresh(db_estudiante)
    return await _adjuntar_programa_estudiante(db, db_estudiante)

@router.delete("/estudiantes/{estudiante_id}/foto", response_model=EstudianteResponse)
async def eliminar_foto(estudiante_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Elimina la foto de un estudiante (foto_url vuelve a null)."""
    result = await db.execute(select(Estudiante).where(Estudiante.id == estudiante_id))
    db_estudiante = result.scalar_one_or_none()
    if not db_estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    if db_estudiante.foto_url:
        _delete_foto(db_estudiante.foto_url)
        db_estudiante.foto_url = None

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "gestion_academica.estudiante.foto_eliminada",
        "source": "mod-gestion-academica",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "data": {"id": db_estudiante.id},
        "metadata": {"request_id": request.headers.get("X-Request-ID", "unknown")}
    }
    db.add(OutboxEvent(event_type=event_payload["event_type"], payload=event_payload))
    await db.commit()
    await db.refresh(db_estudiante)
    return await _adjuntar_programa_estudiante(db, db_estudiante)

def _normalizar_programa(valor) -> str:
    """Normaliza un nombre de programa para compararlo sin acentos ni casing."""
    texto = " ".join(str(valor or "").strip().upper().split())
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def _resolver_programa_id(programa_id, programa_nombre, programas):
    """
    Devuelve el id oficial de programas_estudio o None si la carrera no se
    puede resolver de forma inequívoca. Nunca inventa ni adivina una carrera.
    """
    catalogo = []
    for fila in programas:
        try:
            pid = fila["id"]
            nombre = fila["nombre"]
        except (TypeError, KeyError, IndexError):
            continue
        if pid is not None:
            catalogo.append((pid, _normalizar_programa(nombre)))

    ids_oficiales = {pid for pid, _ in catalogo}

    # Un id explícito solo se acepta si existe en el catálogo oficial.
    id_oficial = None
    if programa_id is not None:
        try:
            pid = int(programa_id)
        except (TypeError, ValueError):
            pid = None
        if pid in ids_oficiales:
            id_oficial = pid

    nombre_oficial = None
    objetivo = _normalizar_programa(programa_nombre)
    if objetivo:
        # Coincidencia exacta primero.
        for pid, nombre_norm in catalogo:
            if nombre_norm == objetivo:
                nombre_oficial = pid
                break

        # Solo se acepta una coincidencia parcial si es inequívoca.
        if nombre_oficial is None:
            coincidencias = [
                pid for pid, nombre_norm in catalogo
                if nombre_norm and (nombre_norm in objetivo or objetivo in nombre_norm)
            ]
            if len(coincidencias) == 1:
                nombre_oficial = coincidencias[0]

    # Si ambos datos existen y se contradicen, no se adivina: se rechaza.
    if id_oficial is not None and nombre_oficial is not None and id_oficial != nombre_oficial:
        return None

    return id_oficial if id_oficial is not None else nombre_oficial


@router.post("/admision/ingesta", status_code=status.HTTP_202_ACCEPTED)
async def ingesta_admitidos(request: Request, data: IngestaMasivaRequest, db: AsyncSession = Depends(get_db)):
    """
    Recibe estudiantes admitidos desde Admisión.
    Verifica sus carreras y evita asignaciones incorrectas.
    """
    estudiantes_creados = 0

    # Consultar las carreras oficiales de SIGA
    programas = (
        await db.execute(
            text("SELECT id, nombre FROM programas_estudio")
        )
    ).mappings().all()

    for admitido in data.admitidos:

        # 1. Evitar registros duplicados por DNI
        existing = await db.execute(
            select(Estudiante).where(
                Estudiante.dni == admitido.dni
            )
        )

        if existing.scalar_one_or_none():
            continue

        # 2. Resolver la carrera verdadera del estudiante
        programa_id = _resolver_programa_id(
            admitido.programa_id,
            admitido.programa_nombre,
            programas
        )

        # PROTECCIÓN NUEVA:
        # No registrar estudiantes con carreras desconocidas
        if programa_id is None:
            await db.rollback()
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No se puede importar al estudiante "
                    f"con DNI {admitido.dni}. "
                    "Su carrera no coincide con ningún "
                    "programa de estudios registrado. "
                    "Importación cancelada."
                )
            )

        # 3. Generar código del estudiante
        year = datetime.now().year
        codigo = f"{year}-{admitido.dni}"

        # 4. Crear estudiante
        db_estudiante = Estudiante(
            codigo_estudiante=codigo,
            dni=admitido.dni,
            nombres=admitido.nombres,
            apellidos=admitido.apellidos,
            programa_id=programa_id,
            celular=admitido.celular,
            email_personal=admitido.email_personal,
            modalidad_admision=admitido.modalidad,
            metadata_admision=admitido.metadata_completa
        )

        db.add(db_estudiante)
        await db.flush()

        # 5. Crear evento para integración con otros módulos
        event_payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "gestion_academica.admision.estudiante_ingresado",
            "source": "mod-gestion-academica",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": "1.0.0",
            "data": {
                "estudiante_id": db_estudiante.id,
                "dni": db_estudiante.dni,
                "nombres": db_estudiante.nombres,
                "apellidos": db_estudiante.apellidos,
                "programa_id": programa_id,
                "periodo_id": admitido.periodo_id,
                "proceso_admision_id": data.proceso_admision_id
            },
            "metadata": {
                "request_id": request.headers.get(
                    "X-Request-ID", "unknown"
                )
            }
        }

        db.add(
            OutboxEvent(
                event_type=event_payload["event_type"],
                payload=event_payload
            )
        )

        estudiantes_creados += 1

    # 6. Confirmar los registros válidos
    await db.commit()

    return {
        "message": "Ingesta procesada",
        "estudiantes_creados": estudiantes_creados
    }

@router.post("/estudiantes/", response_model=EstudianteResponse, status_code=status.HTTP_201_CREATED)
async def crear_estudiante(request: Request, data: EstudianteCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Estudiante).where(
        or_(Estudiante.dni == data.dni, Estudiante.codigo_estudiante == data.codigo_estudiante)
    ))
    existing_student = existing.scalar_one_or_none()
    if existing_student:
        if existing_student.dni == data.dni:
            raise HTTPException(status_code=400, detail="El DNI ya se encuentra registrado en el sistema.")
        else:
            raise HTTPException(status_code=400, detail="El código de estudiante ya existe. Genere uno nuevo.")

    db_estudiante = Estudiante(**data.model_dump())
    db.add(db_estudiante)
    await db.flush()

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "gestion_academica.estudiante.creado",
        "source": "mod-gestion-academica",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "data": {"id": db_estudiante.id, "dni": db_estudiante.dni, "nombre": f"{db_estudiante.nombres} {db_estudiante.apellidos}"},
        "metadata": {"request_id": request.headers.get("X-Request-ID", "unknown")}
    }

    db.add(OutboxEvent(event_type=event_payload["event_type"], payload=event_payload))
    await db.commit()
    await db.refresh(db_estudiante)
    return await _adjuntar_programa_estudiante(db, db_estudiante)

@router.get("/estudiantes/")
async def obtener_estudiantes(programa_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    import traceback
    try:
        query = select(Estudiante).order_by(Estudiante.apellidos)
        if programa_id is not None:
            query = query.where(Estudiante.programa_id == programa_id)
        result = await db.execute(query)
        rows = result.scalars().all()
        result_programas = await db.execute(
            text("SELECT id, nombre, codigo FROM programas_estudio")
        )
        programas = {
            fila["id"]: fila for fila in result_programas.mappings().all()
        }
        print(f"[DEBUG] Estudiantes encontrados: {len(rows)}")
        return [
            {
                "id": r.id,
                "codigo_estudiante": r.codigo_estudiante,
                "dni": r.dni,
                "nombres": r.nombres,
                "apellidos": r.apellidos,
                "estado_academico": r.estado_academico,
                "programa_id": r.programa_id,
                "programa_nombre": programas.get(r.programa_id, {}).get("nombre"),
                "programa_codigo": programas.get(r.programa_id, {}).get("codigo"),
                "foto_url": r.foto_url,
                "email_personal": r.email_personal,
                "email_institucional": r.email_institucional,
                "celular": r.celular,
                "direccion_domicilio": r.direccion_domicilio,
                "fecha_nacimiento": r.fecha_nacimiento.isoformat() if r.fecha_nacimiento else None,
                "pago_matricula": r.pago_matricula,
                "documentos_completos": r.documentos_completos,
                "fecha_limite_documentos": r.fecha_limite_documentos.isoformat() if r.fecha_limite_documentos else None,
                "modalidad_admision": r.modalidad_admision,
                "metadata_admision": r.metadata_admision or {},
            }
            for r in rows
        ]
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[ERROR] obtener_estudiantes: {e}\n{tb}")
        return {"error": str(e), "type": type(e).__name__, "traceback": tb}

@router.get("/estudiantes/siguiente-codigo")
async def obtener_siguiente_codigo(db: AsyncSession = Depends(get_db)):
    """Devuelve el siguiente código de estudiante único del año actual (formato AAAA-000000)."""
    year = datetime.now().year
    prefix = f"{year}-"
    result = await db.execute(
        select(Estudiante.codigo_estudiante).where(Estudiante.codigo_estudiante.like(f"{prefix}%"))
    )
    max_seq = 0
    for codigo in result.scalars().all():
        suffix = str(codigo)[len(prefix):]
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return {"codigo_estudiante": f"{prefix}{max_seq + 1:06d}"}

@router.put("/estudiantes/{estudiante_id}/pago_matricula", response_model=EstudianteResponse)
async def actualizar_pago_matricula(estudiante_id: int, request: Request, pagado: bool = True, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Estudiante).where(Estudiante.id == estudiante_id).with_for_update()
    )
    estudiante = result.scalar_one_or_none()
    if not estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    if estudiante.pago_matricula == pagado:
        # Idempotente: el estado ya es el solicitado (reintento o doble envio).
        # No se modifica nada; el lock de fila se libera al cerrar la sesion.
        return await _adjuntar_programa_estudiante(db, estudiante)

    estudiante.pago_matricula = pagado
    await db.commit()
    await db.refresh(estudiante)
    return await _adjuntar_programa_estudiante(db, estudiante)

@router.get("/estudiantes/{estudiante_id}", response_model=EstudianteResponse)
async def obtener_estudiante(estudiante_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Estudiante).where(Estudiante.id == estudiante_id))
    db_estudiante = result.scalar_one_or_none()
    if not db_estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return await _adjuntar_programa_estudiante(db, db_estudiante)

_ROMANOS = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']

def _titulo_ciclo(numero):
    if numero is None:
        return 'CICLO'
    idx = int(numero) - 1
    return f"CICLO {_ROMANOS[idx]}" if 0 <= idx < len(_ROMANOS) else f"CICLO {numero}"

def _numero_ciclo(nombre_modulo, orden):
    import re
    if nombre_modulo:
        match = re.search(r'ciclo\s*(\d+)', str(nombre_modulo), re.IGNORECASE)
        if match:
            return int(match.group(1))
    return orden if orden is not None else 1

def _seleccionar_programa_boletin(programa_estudiante, programa_matricula, programas):
    """
    Selecciona la fila real de programas_estudio que corresponde al alumno.
    Prefiere el programa del estudiante; usa el de la matrícula solo cuando
    aquel no existe en el catálogo. No inventa programas ni relaciones.
    """
    candidatos = []
    for pid in (programa_estudiante, programa_matricula):
        if pid is not None and pid not in candidatos:
            candidatos.append(pid)
    for pid in candidatos:
        for fila in programas:
            if fila["id"] == pid:
                return fila
    return None

async def _obtener_notas_boletin(db, estudiante_id, unidad_ids):
    """
    Notas reales del estudiante, limitadas a las unidades de la malla elegida.

    `evaluacion_registros.unidad_didactica_id` puede apuntar a una unidad de
    programa_unidades o de unidades_plan (Evaluación consulta ambas). Para no
    confundir IDs de tablas distintas, solo se acepta un registro cuando su
    unidad pertenece a la malla seleccionada; si no, se usa la unidad real de
    la matrícula asociada al registro (`matricula_detalle_id`).
    """
    from sqlalchemy import text

    if not unidad_ids:
        return {}

    placeholders = ','.join(f':u{i}' for i in range(len(unidad_ids)))
    parametros = {"eid": estudiante_id}
    parametros.update({f'u{i}': uid for i, uid in enumerate(unidad_ids)})

    result_eval = await db.execute(
        text(f"""
            SELECT er.unidad_didactica_id,
                   md.unidad_didactica_id AS matricula_unidad_id,
                   er.nota_c1, er.nota_c2, er.nota_c3, er.nota_final,
                   er.estado, er.periodo_id
            FROM evaluacion_registros er
            LEFT JOIN matricula_detalles md ON md.id = er.matricula_detalle_id
            WHERE er.estudiante_id = :eid
              AND (er.nota_final IS NOT NULL OR er.nota_c1 IS NOT NULL
                   OR er.nota_c2 IS NOT NULL OR er.nota_c3 IS NOT NULL)
              AND (er.unidad_didactica_id IN ({placeholders})
                   OR md.unidad_didactica_id IN ({placeholders}))
        """),
        parametros
    )
    evals = result_eval.mappings().all()

    result_per = await db.execute(text("SELECT id, codigo FROM periodos_academicos"))
    periodos = {p["id"]: p["codigo"] for p in result_per.mappings().all()}

    permitidas = set(unidad_ids)
    mejor = {}
    for e in evals:
        uid = e["unidad_didactica_id"]
        if uid not in permitidas:
            uid = e["matricula_unidad_id"]
        if uid not in permitidas:
            continue

        parciales = [n for n in (e["nota_c1"], e["nota_c2"], e["nota_c3"]) if n is not None]
        nota = e["nota_final"]
        if nota is None and parciales:
            nota = round(sum(parciales) / len(parciales))
        if nota is None:
            continue

        clave = (1 if e["estado"] == 'aprobado' else 0, nota, e["periodo_id"] or 0)
        actual = mejor.get(uid)
        if actual is None or clave > actual["_clave"]:
            mejor[uid] = {
                "nota": nota,
                "nota_c1": e["nota_c1"],
                "nota_c2": e["nota_c2"],
                "nota_c3": e["nota_c3"],
                "estado": e["estado"],
                "periodo_codigo": periodos.get(e["periodo_id"]),
                "_clave": clave,
            }
    return mejor

async def _obtener_docentes_boletin(db, unidad_ids, periodo_id=None, programa_id=None):
    """Docente real de carga lectiva, restringido al programa cuando se conoce."""
    from sqlalchemy import text

    if not unidad_ids:
        return {}

    placeholders = ','.join(f':u{i}' for i in range(len(unidad_ids)))
    parametros = {f'u{i}': uid for i, uid in enumerate(unidad_ids)}
    filtro_programa = ""
    if programa_id is not None:
        filtro_programa = " AND cl.programa_id = :prog_id"
        parametros["prog_id"] = programa_id

    result_cl = await db.execute(
        text(f"""
            SELECT cl.unidad_didactica_id, cl.periodo_id, cl.turno, cl.seccion, cu.full_name
            FROM carga_lectiva cl
            LEFT JOIN core_users cu ON cu.id = cl.docente_id
            WHERE cl.unidad_didactica_id IN ({placeholders}){filtro_programa}
        """),
        parametros
    )

    docentes_por_unidad = {}
    for row in result_cl.mappings().all():
        uid = row["unidad_didactica_id"]
        docentes_por_unidad.setdefault(uid, []).append({
            "docente": row["full_name"],
            "turno": row["turno"],
            "seccion": row["seccion"],
            "periodo_id": row["periodo_id"],
        })
    return docentes_por_unidad

def _armar_ciclos_boletin(modulos, unidades, mejor, docentes_por_unidad, clave_modulo_unidad, numero_modulo, periodo_id=None):
    """Arma el contrato de ciclos del boletín desde la malla ya seleccionada."""
    unidades_por_modulo = {}
    for u in unidades:
        unidades_por_modulo.setdefault(u[clave_modulo_unidad], []).append(u)

    ciclos = {}
    for mod in modulos:
        num = numero_modulo(mod)
        ciclo = ciclos.setdefault(num, {"ciclo": num, "titulo": _titulo_ciclo(num), "unidades": []})
        for u in unidades_por_modulo.get(mod["id"], []):
            reg = mejor.get(u["id"])
            opciones = docentes_por_unidad.get(u["id"]) or []
            docente = None
            if opciones:
                periodo_eval = reg["_clave"][2] if reg else None
                docente = next((o for o in opciones if periodo_eval and o["periodo_id"] == periodo_eval), None)
                if docente is None and periodo_id:
                    docente = next((o for o in opciones if o["periodo_id"] == periodo_id), None)
                if docente is None:
                    docente = max(opciones, key=lambda o: o["periodo_id"] or 0)
            ciclo["unidades"].append({
                "nombre": u["nombre"],
                "codigo": u.get("codigo"),
                "creditos": u["creditos"],
                "horas": u.get("horas"),
                "tipo": u.get("tipo"),
                "nota": reg["nota"] if reg else None,
                "nota_c1": reg["nota_c1"] if reg else None,
                "nota_c2": reg["nota_c2"] if reg else None,
                "nota_c3": reg["nota_c3"] if reg else None,
                "estado": reg["estado"] if reg else "no_cursado",
                "periodo_codigo": reg["periodo_codigo"] if reg else None,
                "docente": docente["docente"] if docente else None,
                "turno": docente["turno"] if docente else None,
                "seccion": docente["seccion"] if docente else None,
            })

    salida = []
    for num in sorted(ciclos):
        c = ciclos[num]
        notas = [u["nota"] for u in c["unidades"] if u["nota"] is not None]
        c["promedio"] = round(sum(notas) / len(notas), 2) if notas else None
        c["creditos_ciclo"] = sum((u["creditos"] or 0) for u in c["unidades"])
        c["creditos_aprobados"] = sum((u["creditos"] or 0) for u in c["unidades"] if u["estado"] == 'aprobado')
        c["completado"] = len(c["unidades"]) > 0 and all(u["estado"] == 'aprobado' for u in c["unidades"])
        salida.append(c)

    return salida, len(salida)

async def _construir_ciclos_programa(db, estudiante_id, programa_id, periodo_id=None):
    """Malla operativa del estudiante: programa_modulos -> programa_unidades."""
    from sqlalchemy import text

    if not programa_id:
        return [], 0

    result_mod = await db.execute(
        text("""
            SELECT id, nombre, periodo, orden
            FROM programa_modulos
            WHERE programa_id = :prog_id
            ORDER BY periodo, orden, id
        """),
        {"prog_id": programa_id}
    )
    modulos = result_mod.mappings().all()
    if not modulos:
        return [], 0

    modulo_ids = [m["id"] for m in modulos]
    placeholders = ','.join(f':m{i}' for i in range(len(modulo_ids)))
    result_uni = await db.execute(
        text(f"""
            SELECT u.id, u.programa_modulo_id, u.nombre, u.creditos,
                   (COALESCE(u.horas_teoria, 0) + COALESCE(u.horas_practica, 0)) AS horas,
                   u.orden
            FROM programa_unidades u
            WHERE u.programa_modulo_id IN ({placeholders})
            ORDER BY u.programa_modulo_id, u.orden, u.id
        """),
        {f'm{i}': mid for i, mid in enumerate(modulo_ids)}
    )
    unidades = result_uni.mappings().all()

    mejor = await _obtener_notas_boletin(db, estudiante_id, [u["id"] for u in unidades])
    docentes = await _obtener_docentes_boletin(
        db, [u["id"] for u in unidades], periodo_id, programa_id
    )

    def _numero_modulo(mod):
        return _numero_ciclo(
            mod["nombre"],
            mod["periodo"] if mod["periodo"] is not None else mod["orden"],
        )

    return _armar_ciclos_boletin(
        modulos, unidades, mejor, docentes, "programa_modulo_id", _numero_modulo, periodo_id
    )

async def _construir_ciclos(db, estudiante_id, plan_id, periodo_id=None):
    """Documento histórico: agrupa las unidades del plan por ciclo con la mejor nota del estudiante."""
    from sqlalchemy import text

    if not plan_id:
        return [], 0

    result_mod = await db.execute(
        text("SELECT id, nombre, orden FROM modulos_plan WHERE plan_id = :pid ORDER BY orden, id"),
        {"pid": plan_id}
    )
    modulos = result_mod.mappings().all()
    if not modulos:
        return [], 0

    modulo_ids = [m["id"] for m in modulos]
    placeholders = ','.join(f':m{i}' for i in range(len(modulo_ids)))
    result_uni = await db.execute(
        text(f"""
            SELECT id, modulo_id, nombre, codigo, creditos, horas, tipo, orden
            FROM unidades_plan
            WHERE modulo_id IN ({placeholders})
            ORDER BY modulo_id, orden, id
        """),
        {f'm{i}': mid for i, mid in enumerate(modulo_ids)}
    )
    unidades = result_uni.mappings().all()

    mejor = await _obtener_notas_boletin(db, estudiante_id, [u["id"] for u in unidades])
    docentes = await _obtener_docentes_boletin(db, [u["id"] for u in unidades], periodo_id)

    def _numero_modulo(mod):
        return _numero_ciclo(mod["nombre"], mod["orden"])

    return _armar_ciclos_boletin(
        modulos, unidades, mejor, docentes, "modulo_id", _numero_modulo, periodo_id
    )

async def _nombre_unidad_boletin(db, unidad_id, programa_id=None):
    """
    Nombre real de una unidad didáctica. Evaluación usa primero el catálogo
    del programa; se replica ese orden para no mostrar el nombre de una unidad
    del plan cuando el ID coincide con una unidad del programa.
    """
    from sqlalchemy import text

    if programa_id is not None:
        result = await db.execute(
            text("""
                SELECT pu.nombre
                FROM programa_unidades pu
                JOIN programa_modulos pm ON pm.id = pu.programa_modulo_id
                WHERE pu.id = :uid AND pm.programa_id = :prog_id
            """),
            {"uid": unidad_id, "prog_id": programa_id}
        )
        fila = result.mappings().first()
        if fila and fila["nombre"]:
            return fila["nombre"]

    result = await db.execute(
        text("SELECT nombre FROM programa_unidades WHERE id = :uid"),
        {"uid": unidad_id}
    )
    fila = result.mappings().first()
    if fila and fila["nombre"]:
        return fila["nombre"]

    result = await db.execute(
        text("SELECT nombre FROM unidades_plan WHERE id = :uid"),
        {"uid": unidad_id}
    )
    fila = result.mappings().first()
    if fila and fila["nombre"]:
        return fila["nombre"]

    return f"Unidad {unidad_id}"

async def _periodo_por_defecto_boletin(db, estudiante_id):
    """Periodo por defecto del boletin: ultima matricula del estudiante;
    si no tiene, el periodo vigente; si no, el mas reciente registrado."""
    from sqlalchemy import text

    result = await db.execute(
        text("""
            SELECT m.periodo_id
            FROM matriculas m
            JOIN periodos_academicos pa ON pa.id = m.periodo_id
            WHERE m.estudiante_id = :eid
            ORDER BY pa.fecha_inicio DESC NULLS LAST, m.id DESC
            LIMIT 1
        """),
        {"eid": estudiante_id},
    )
    periodo_id = result.scalars().first()
    if periodo_id:
        return periodo_id

    result = await db.execute(
        text("""
            SELECT id FROM periodos_academicos
            ORDER BY CASE estado WHEN 'en_curso' THEN 0 WHEN 'matricula_abierta' THEN 1 ELSE 2 END,
                     fecha_inicio DESC NULLS LAST, id DESC
            LIMIT 1
        """)
    )
    periodo_id = result.scalars().first()
    if periodo_id:
        return periodo_id

    raise HTTPException(status_code=404, detail="No hay periodos academicos registrados")

@router.get("/estudiantes/{estudiante_id}/boletin")
async def obtener_boletin(estudiante_id: int, periodo_id: Optional[int] = None, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text

    result_est = await db.execute(select(Estudiante).where(Estudiante.id == estudiante_id))
    estudiante = result_est.scalar_one_or_none()
    if not estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    if periodo_id is None:
        periodo_id = await _periodo_por_defecto_boletin(db, estudiante_id)

    result_mat = await db.execute(
        select(Matricula).options(selectinload(Matricula.detalles))
        .where(Matricula.estudiante_id == estudiante_id)
        .where(Matricula.periodo_id == periodo_id)
    )
    matricula = result_mat.scalar_one_or_none()

    result_periodo = await db.execute(
        text("SELECT codigo, fecha_fin_matricula_regular, fecha_fin_matricula_extemporanea FROM periodos_academicos WHERE id = :pid"),
        {"pid": periodo_id}
    )
    periodo_row = result_periodo.mappings().first()
    periodo_codigo = periodo_row["codigo"] if periodo_row else "N/A"

    result_programas = await db.execute(
        text("""
            SELECT pr.id, pr.nombre AS programa_nombre, pr.plan_estudio_id,
                   p.creditos_totales, p.nombre AS plan_nombre, p.nivel_formativo
            FROM programas_estudio pr
            LEFT JOIN planes_estudio p ON p.id = pr.plan_estudio_id
        """)
    )
    programas = result_programas.mappings().all()
    fila_programa = _seleccionar_programa_boletin(
        estudiante.programa_id,
        matricula.programa_id if matricula else None,
        programas,
    )
    programa_id = fila_programa["id"] if fila_programa else estudiante.programa_id
    programa_nombre = fila_programa["programa_nombre"] if fila_programa else None
    creditos_totales = (
        fila_programa["creditos_totales"]
        if fila_programa and fila_programa["creditos_totales"] is not None
        else 0
    )

    result_creditos_aprob = await db.execute(
        text("""
            SELECT COALESCE(SUM(md.creditos), 0) as total
            FROM matricula_detalles md
            JOIN matriculas m ON md.matricula_id = m.id
            WHERE m.estudiante_id = :eid
            AND md.estado_curso = 'aprobado'
        """),
        {"eid": estudiante_id}
    )
    creditos_aprobados = result_creditos_aprob.scalar()

    cursos_periodo = []
    if matricula and matricula.detalles:
        for det in matricula.detalles:
            nombre_unidad = await _nombre_unidad_boletin(
                db, det.unidad_didactica_id, programa_id
            )

            result_eval = await db.execute(
                text("""
                    SELECT nota_c1, nota_c2, nota_c3, nota_final, estado
                    FROM evaluacion_registros
                    WHERE matricula_detalle_id = :md_id
                """),
                {"md_id": det.id}
            )
            eval_row = result_eval.mappings().first()

            cursos_periodo.append({
                "unidad_nombre": nombre_unidad,
                "creditos": det.creditos,
                "nota_c1": eval_row["nota_c1"] if eval_row else None,
                "nota_c2": eval_row["nota_c2"] if eval_row else None,
                "nota_c3": eval_row["nota_c3"] if eval_row else None,
                "nota_final": eval_row["nota_final"] if eval_row else None,
                "estado": eval_row["estado"] if eval_row else det.estado_curso,
            })

    notas_finales = [c["nota_final"] for c in cursos_periodo if c["nota_final"] is not None]
    promedio_periodo = round(sum(notas_finales) / len(notas_finales)) if notas_finales else None
    aprobados = sum(1 for c in cursos_periodo if c["estado"] == "aprobado")
    desaprobados = sum(1 for c in cursos_periodo if c["estado"] == "desaprobado")

    result_hist = await db.execute(
        text("""
            SELECT DISTINCT m.periodo_id, pa.codigo as periodo_codigo
            FROM matriculas m
            JOIN periodos_academicos pa ON pa.id = m.periodo_id
            WHERE m.estudiante_id = :eid AND m.periodo_id != :current_pid
            ORDER BY pa.codigo
        """),
        {"eid": estudiante_id, "current_pid": periodo_id}
    )
    periodos_anteriores = result_hist.mappings().all()

    historial = []
    for p in periodos_anteriores:
        result_evals = await db.execute(
            text("""
                SELECT er.nota_final, er.estado
                FROM evaluacion_registros er
                WHERE er.estudiante_id = :eid AND er.periodo_id = :pid
            """),
            {"eid": estudiante_id, "pid": p["periodo_id"]}
        )
        evals = result_evals.mappings().all()
        notas_p = [e["nota_final"] for e in evals if e["nota_final"] is not None]
        hist_aprob = sum(1 for e in evals if e["estado"] == "aprobado")
        hist_desaprob = sum(1 for e in evals if e["estado"] == "desaprobado")
        historial.append({
            "periodo_codigo": p["periodo_codigo"],
            "promedio": round(sum(notas_p) / len(notas_p)) if notas_p else None,
            "cursos_aprobados": hist_aprob,
            "cursos_desaprobados": hist_desaprob,
        })

    result_observ = await db.execute(
        text("SELECT observaciones FROM matriculas WHERE estudiante_id = :eid AND periodo_id = :pid"),
        {"eid": estudiante_id, "pid": periodo_id}
    )
    observ_row = result_observ.mappings().first()
    observaciones = observ_row["observaciones"] if observ_row else None

    plan_estudio_id = fila_programa["plan_estudio_id"] if fila_programa else None
    if not plan_estudio_id:
        # Plan de origen registrado en el expediente (alumnos históricos).
        plan_estudio_id = getattr(estudiante, "plan_estudios_id", None)

    # La malla operativa de SIGA es la del programa (la usan matrícula y
    # evaluación). El plan se usa solo si ese programa no tiene malla cargada.
    ciclos, ciclos_totales = await _construir_ciclos_programa(
        db, estudiante_id, programa_id, periodo_id
    )
    if not ciclos:
        ciclos, ciclos_totales = await _construir_ciclos(
            db, estudiante_id, plan_estudio_id, periodo_id
        )
    ciclos_completados = sum(1 for c in ciclos if c.get("completado"))

    return {
        "estudiante": {
            "foto_url": estudiante.foto_url,
            "nombres": estudiante.nombres,
            "apellidos": estudiante.apellidos,
            "codigo_estudiante": estudiante.codigo_estudiante,
            "dni": estudiante.dni,
            "celular": estudiante.celular,
            "email_personal": estudiante.email_personal,
            "programa_nombre": programa_nombre,
            "periodo_codigo": periodo_codigo,
            "fecha_emision": datetime.utcnow().strftime("%d/%m/%Y"),
        },
        "matricula_estado": {
            "pago_matricula": estudiante.pago_matricula,
            "tipo_ingreso": matricula.tipo_ingreso if matricula else None,
            "estado_matricula": matricula.estado_matricula if matricula else "sin_matricula",
            "fecha_fin_matricula_regular": str(periodo_row["fecha_fin_matricula_regular"]) if periodo_row and periodo_row["fecha_fin_matricula_regular"] else None,
            "fecha_fin_matricula_extemporanea": str(periodo_row["fecha_fin_matricula_extemporanea"]) if periodo_row and periodo_row["fecha_fin_matricula_extemporanea"] else None,
        },
        "estado_academico": estudiante.estado_academico,
        "progreso_creditos": {
            "creditos_aprobados": creditos_aprobados,
            "creditos_totales": creditos_totales,
            "porcentaje": round((creditos_aprobados / creditos_totales) * 100) if creditos_totales > 0 else 0,
        },
        "cursos_periodo": cursos_periodo,
        "ciclos": ciclos,
        "resumen": {
            "promedio_general": promedio_periodo,
            "cursos_aprobados": aprobados,
            "cursos_desaprobados": desaprobados,
            "total_cursos": len(cursos_periodo),
            "ciclos_completados": ciclos_completados,
            "ciclos_totales": ciclos_totales,
        },
        "historial": historial,
        "observaciones": observaciones,
    }

@router.put("/estudiantes/{estudiante_id}", response_model=EstudianteResponse)
async def actualizar_estudiante(estudiante_id: int, data: EstudianteUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Estudiante).where(Estudiante.id == estudiante_id))
    db_estudiante = result.scalar_one_or_none()
    if not db_estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_estudiante, key, value)

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "gestion_academica.estudiante.actualizado",
        "source": "mod-gestion-academica",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "data": {"id": db_estudiante.id},
        "metadata": {"request_id": request.headers.get("X-Request-ID", "unknown")}
    }

    db.add(OutboxEvent(event_type=event_payload["event_type"], payload=event_payload))
    await db.commit()
    await db.refresh(db_estudiante)
    return await _adjuntar_programa_estudiante(db, db_estudiante)

@router.delete("/estudiantes/{estudiante_id}")
async def eliminar_estudiante(estudiante_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Estudiante).where(Estudiante.id == estudiante_id))
    db_estudiante = result.scalar_one_or_none()
    if not db_estudiante:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    await db.delete(db_estudiante)

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "gestion_academica.estudiante.eliminado",
        "source": "mod-gestion-academica",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "data": {"id": estudiante_id},
        "metadata": {"request_id": request.headers.get("X-Request-ID", "unknown")}
    }

    db.add(OutboxEvent(event_type=event_payload["event_type"], payload=event_payload))
    await db.commit()
    return {"message": "Estudiante eliminado"}

@router.post("/matriculas/", response_model=MatriculaResponse, status_code=status.HTTP_201_CREATED)
async def realizar_matricula(request: Request, data: MatriculaCreate, db: AsyncSession = Depends(get_db)):
    # Validar si ya está matriculado en este periodo
    from sqlalchemy.future import select
    existing = await db.execute(
        select(Matricula).where(
            Matricula.estudiante_id == data.estudiante_id,
            Matricula.periodo_id == data.periodo_id,
            Matricula.estado_matricula != 'anulado'
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="El estudiante ya cuenta con una matrícula registrada para este periodo académico.")

    # Validar créditos
    total_creditos = sum(d.creditos for d in data.detalles)
    if total_creditos < 1 or total_creditos > 40:
        raise HTTPException(status_code=400, detail=f"La matrícula tiene {total_creditos} créditos. Debe estar entre 1 y 40 créditos")

    # Separar detalles
    matricula_data = data.model_dump(exclude={"detalles"})
    db_matricula = Matricula(**matricula_data)
    db.add(db_matricula)
    await db.flush() # Para obtener db_matricula.id

    for det in data.detalles:
        db_detalle = MatriculaDetalle(matricula_id=db_matricula.id, **det.model_dump())
        db.add(db_detalle)

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "gestion_academica.matricula.confirmada",
        "source": "mod-gestion-academica",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "data": {"matricula_id": db_matricula.id, "estudiante_id": db_matricula.estudiante_id, "creditos": total_creditos},
        "metadata": {"request_id": request.headers.get("X-Request-ID", "unknown")}
    }

    db.add(OutboxEvent(event_type=event_payload["event_type"], payload=event_payload))
    await db.commit()

    result = await db.execute(select(Matricula).options(selectinload(Matricula.detalles)).where(Matricula.id == db_matricula.id))
    return result.scalar_one()

@router.get("/matriculas/", response_model=List[MatriculaResponse])
async def obtener_matriculas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Matricula).options(selectinload(Matricula.detalles)).order_by(Matricula.created_at.desc()))
    return result.scalars().all()

@router.get("/matriculas/estudiante/{estudiante_id}", response_model=List[MatriculaResponse])
async def obtener_matriculas_estudiante(estudiante_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Matricula).options(selectinload(Matricula.detalles)).where(Matricula.estudiante_id == estudiante_id).order_by(Matricula.created_at.desc()))
    return result.scalars().all()

@router.get("/matriculas/unidad/{unidad_id}/periodo/{periodo_id}")
async def obtener_estudiantes_por_unidad(unidad_id: int, periodo_id: int, db: AsyncSession = Depends(get_db)):
    query = (
        select(Estudiante, MatriculaDetalle.id.label("matricula_detalle_id"))
        .join(Matricula, Matricula.estudiante_id == Estudiante.id)
        .join(MatriculaDetalle, MatriculaDetalle.matricula_id == Matricula.id)
        .where(Matricula.periodo_id == periodo_id)
        .where(MatriculaDetalle.unidad_didactica_id == unidad_id)
        .where(Matricula.estado_matricula != "anulada")
    )
    result = await db.execute(query)
    rows = result.all()

    response = []
    for est, det_id in rows:
        est_dict = EstudianteResponse.model_validate(est).model_dump()
        est_dict["matricula_detalle_id"] = det_id
        response.append(est_dict)

    return response

@router.post("/matriculas/unidad/{unidad_id}/periodo/{periodo_id}/sincronizar")
async def sincronizar_estudiantes_seccion(unidad_id: int, periodo_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Sincroniza y matricula a los estudiantes activos del programa y ciclo que corresponda a esta unidad didáctica
    para que el docente disponga inmediatamente de la nómina completa en su registro de calificaciones.
    """
    query_ud = text("""
        SELECT u.id, u.creditos, m.programa_id, m.periodo as ciclo
        FROM programa_unidades u
        JOIN programa_modulos m ON u.programa_modulo_id = m.id
        WHERE u.id = :uid
    """)
    res_ud = await db.execute(query_ud, {"uid": unidad_id})
    row_ud = res_ud.fetchone()

    prog_id = row_ud[2] if row_ud else None
    creds = row_ud[1] if row_ud and row_ud[1] else 2
    ciclo = row_ud[3] if row_ud and row_ud[3] else 1

    # Buscar estudiantes que pertenezcan estrictamente al programa Y al ciclo de la unidad
    if prog_id:
        res_est = await db.execute(
            select(Estudiante)
            .where(Estudiante.programa_id == prog_id)
            .where(Estudiante.ciclo_actual == ciclo)
        )
        estudiantes = res_est.scalars().all()
    else:
        estudiantes = []

    if not estudiantes:
        return []

    for est in estudiantes:
        res_mat = await db.execute(
            select(Matricula).where(Matricula.estudiante_id == est.id).where(Matricula.periodo_id == periodo_id)
        )
        db_mat = res_mat.scalar_one_or_none()
        if not db_mat:
            db_mat = Matricula(
                estudiante_id=est.id,
                programa_id=prog_id or est.programa_id,
                periodo_id=periodo_id,
                estado_matricula="confirmada",
                ciclo=ciclo,
                tipo_ingreso="regular",
                casuistica="regular"
            )
            db.add(db_mat)
            await db.flush()

        res_det = await db.execute(
            select(MatriculaDetalle)
            .where(MatriculaDetalle.matricula_id == db_mat.id)
            .where(MatriculaDetalle.unidad_didactica_id == unidad_id)
        )
        db_det = res_det.scalar_one_or_none()
        if not db_det:
            db_det = MatriculaDetalle(
                matricula_id=db_mat.id,
                unidad_didactica_id=unidad_id,
                estado_curso="cursando",
                creditos=creds
            )
            db.add(db_det)

    await db.commit()
    return await obtener_estudiantes_por_unidad(unidad_id, periodo_id, db)

@router.delete("/matriculas/{matricula_id}")
async def anular_matricula(matricula_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Matricula).where(Matricula.id == matricula_id))
    db_matricula = result.scalar_one_or_none()
    if not db_matricula:
        raise HTTPException(status_code=404, detail="Matrícula no encontrada")

    db_matricula.estado_matricula = "anulada"

    event_payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "gestion_academica.matricula.anulada",
        "source": "mod-gestion-academica",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "data": {"matricula_id": matricula_id, "estudiante_id": db_matricula.estudiante_id},
        "metadata": {"request_id": request.headers.get("X-Request-ID", "unknown")}
    }

    db.add(OutboxEvent(event_type=event_payload["event_type"], payload=event_payload))
    await db.commit()
    return {"message": "Matrícula anulada correctamente"}

# ================================
# FASE 4: TRAMITES Y CASUISTICAS
# ================================
from schemas import (
    SolicitudTramiteCreate, SolicitudTramiteResponse,
    ResolucionConvalidacionCreate, ResolucionConvalidacionResponse,
    BeneficioEstudianteCreate, BeneficioEstudianteResponse
)
from models import SolicitudTramite, ResolucionConvalidacion, ConvalidacionDetalle, BeneficioEstudiante

ESTADOS_TRAMITE = {"pendiente", "en_proceso", "emitido", "rechazado", "aprobado"}

@router.post("/tramites/", response_model=SolicitudTramiteResponse, status_code=status.HTTP_201_CREATED)
async def crear_tramite(data: SolicitudTramiteCreate, db: AsyncSession = Depends(get_db)):
    db_tramite = SolicitudTramite(estado="pendiente", **data.model_dump())
    db.add(db_tramite)
    await db.commit()
    await db.refresh(db_tramite)
    return db_tramite

@router.get("/tramites/", response_model=List[SolicitudTramiteResponse])
async def obtener_tramites(db: AsyncSession = Depends(get_db)):
    # Ordenar por id evita que registros históricos sin fecha queden fuera de
    # orden o que una fecha NULL rompa la consulta.
    result = await db.execute(select(SolicitudTramite).order_by(SolicitudTramite.id.desc()))
    return result.scalars().all()

@router.put("/tramites/{tramite_id}/estado", response_model=SolicitudTramiteResponse)
async def actualizar_estado_tramite(tramite_id: int, estado: str, db: AsyncSession = Depends(get_db)):
    if estado not in ESTADOS_TRAMITE:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Use: {', '.join(sorted(ESTADOS_TRAMITE))}")
    result = await db.execute(select(SolicitudTramite).where(SolicitudTramite.id == tramite_id))
    db_tramite = result.scalar_one_or_none()
    if not db_tramite:
        raise HTTPException(status_code=404, detail="Trámite no encontrado")

    db_tramite.estado = estado
    if estado in ["emitido", "rechazado", "aprobado"]:
        db_tramite.fecha_resolucion = datetime.utcnow().date()

    await db.commit()
    await db.refresh(db_tramite)
    return db_tramite

@router.post("/convalidaciones/", response_model=ResolucionConvalidacionResponse, status_code=status.HTTP_201_CREATED)
async def registrar_convalidacion(data: ResolucionConvalidacionCreate, db: AsyncSession = Depends(get_db)):
    existente = await db.execute(select(ResolucionConvalidacion).where(ResolucionConvalidacion.numero_resolucion == data.numero_resolucion))
    if existente.scalars().first():
        raise HTTPException(status_code=409, detail="Ya existe una resolución con ese número")
    if not data.detalles:
        raise HTTPException(status_code=400, detail="Debe indicar al menos una unidad convalidada")
    conval_data = data.model_dump(exclude={"detalles"})
    db_resolucion = ResolucionConvalidacion(**conval_data)
    db.add(db_resolucion)
    await db.flush() # para obtener el ID de la resolucion

    for det in data.detalles:
        db_detalle = ConvalidacionDetalle(resolucion_id=db_resolucion.id, **det.model_dump())
        db.add(db_detalle)

    await db.commit()
    # Refresh with relation
    result = await db.execute(select(ResolucionConvalidacion).options(selectinload(ResolucionConvalidacion.detalles)).where(ResolucionConvalidacion.id == db_resolucion.id))
    return result.scalar_one()

@router.get("/convalidaciones/", response_model=List[ResolucionConvalidacionResponse])
async def listar_convalidaciones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ResolucionConvalidacion)
        .options(selectinload(ResolucionConvalidacion.detalles))
        .order_by(ResolucionConvalidacion.fecha_emision.desc(), ResolucionConvalidacion.id.desc())
    )
    return result.scalars().all()

@router.get("/convalidaciones/estudiante/{estudiante_id}", response_model=List[ResolucionConvalidacionResponse])
async def obtener_convalidaciones_estudiante(estudiante_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ResolucionConvalidacion).options(selectinload(ResolucionConvalidacion.detalles)).where(ResolucionConvalidacion.estudiante_id == estudiante_id))
    return result.scalars().all()

@router.post("/beneficios/", response_model=BeneficioEstudianteResponse, status_code=status.HTTP_201_CREATED)
async def registrar_beneficio(data: BeneficioEstudianteCreate, db: AsyncSession = Depends(get_db)):
    if not 0 < data.porcentaje_descuento <= 100:
        raise HTTPException(status_code=400, detail="El porcentaje de descuento debe estar entre 0 y 100")
    db_beneficio = BeneficioEstudiante(**data.model_dump())
    db.add(db_beneficio)
    await db.commit()
    await db.refresh(db_beneficio)
    return db_beneficio

@router.get("/beneficios/", response_model=List[BeneficioEstudianteResponse])
async def listar_beneficios(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BeneficioEstudiante).order_by(BeneficioEstudiante.id.desc()))
    return result.scalars().all()

@router.put("/beneficios/{beneficio_id}/desactivar", response_model=BeneficioEstudianteResponse)
async def desactivar_beneficio(beneficio_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BeneficioEstudiante).where(BeneficioEstudiante.id == beneficio_id))
    db_beneficio = result.scalar_one_or_none()
    if not db_beneficio:
        raise HTTPException(status_code=404, detail="Beneficio no encontrado")
    db_beneficio.activo = False
    await db.commit()
    await db.refresh(db_beneficio)
    return db_beneficio

@router.get("/beneficios/estudiante/{estudiante_id}", response_model=List[BeneficioEstudianteResponse])
async def obtener_beneficios_estudiante(estudiante_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BeneficioEstudiante).where(BeneficioEstudiante.estudiante_id == estudiante_id, BeneficioEstudiante.activo == True))
    return result.scalars().all()
