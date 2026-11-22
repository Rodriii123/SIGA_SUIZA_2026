
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
