import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { apiClient } from '../../core/api/client';
import { useToast } from '../../core/ui/ToastContext';
import {
  X,
  Calendar,
  Plus,
  Clock,
  ArrowRight,
  Edit3,
  Search,
  AlertTriangle,
  Info,
  Save,
  RotateCcw,
  ShieldCheck,
  RefreshCw
} from 'lucide-react';
import {
  ESTADOS_PERIODO,
  FORMULARIO_VACIO,
  coincidePeriodo,
  formatearFecha,
  normalizarCodigo,
  resumenRelaciones,
  validarPeriodo
} from './periodValidation';

const inputBase = 'w-full px-3 py-2 bg-white border rounded-xl text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all disabled:bg-slate-100 disabled:text-slate-500';

function CampoFormulario({ id, etiqueta, tipo = 'text', valor, onChange, error, deshabilitado, placeholder, requerido = true, monoespacio = false }) {
  const clase = `${inputBase} ${error ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-200' : 'border-slate-200'} ${monoespacio ? 'font-mono uppercase' : ''}`;

  return (
    <div>
      <label htmlFor={id} className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1">
        {etiqueta}
      </label>
      <input
        id={id}
        type={tipo}
        className={clase}
        value={valor ?? ''}
        onChange={(evento) => onChange(evento.target.value)}
        disabled={deshabilitado}
        placeholder={placeholder}
        required={requerido}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
      />
      {error && (
        <p id={`${id}-error`} className="mt-1 text-[11px] font-medium text-rose-600 flex items-start gap-1">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}
    </div>
  );
}

function BadgeEstado({ estado }) {
  const valor = String(estado ?? '').toLowerCase();
  const configuracion = {
    planificacion: { texto: 'Planificación', clase: 'bg-amber-50 text-amber-700 border-amber-200/60', punto: 'bg-amber-500' },
    matricula_abierta: { texto: 'Matrícula Abierta', clase: 'bg-sky-50 text-sky-700 border-sky-200/60', punto: 'bg-sky-500 animate-pulse' },
    activo: { texto: 'En Curso', clase: 'bg-emerald-50 text-emerald-700 border-emerald-200/60', punto: 'bg-emerald-500 animate-pulse' },
    en_curso: { texto: 'En Curso', clase: 'bg-emerald-50 text-emerald-700 border-emerald-200/60', punto: 'bg-emerald-500 animate-pulse' },
    historico: { texto: 'Histórico', clase: 'bg-slate-100 text-slate-600 border-slate-200', punto: 'bg-slate-400' },
    cerrado: { texto: 'Cerrado', clase: 'bg-slate-100 text-slate-600 border-slate-200', punto: 'bg-slate-400' }
  }[valor] || { texto: estado || 'Sin estado', clase: 'bg-slate-100 text-slate-600 border-slate-200', punto: 'bg-slate-400' };

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${configuracion.clase}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${configuracion.punto}`} />
      {configuracion.texto}
    </span>
  );
}

function soloFecha(valor) {
  const texto = String(valor ?? '');
  return /^\d{4}-\d{2}-\d{2}/.test(texto) ? texto.slice(0, 10) : '';
}

export function PeriodManager({ onClose, onUpdate }) {
  const { success, error, confirm: confirmar } = useToast();

  const [periods, setPeriods] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [errorCarga, setErrorCarga] = useState('');
  const [formulario, setFormulario] = useState({ ...FORMULARIO_VACIO });
  const [formularioInicial, setFormularioInicial] = useState({ ...FORMULARIO_VACIO });
  const [editandoId, setEditandoId] = useState(null);
  const [errores, setErrores] = useState({});
  const [guardando, setGuardando] = useState(false);
  const [cambiandoEstadoId, setCambiandoEstadoId] = useState(null);
  const [busqueda, setBusqueda] = useState('');
  const [filtroEstado, setFiltroEstado] = useState('todos');

  const cargarPeriodos = useCallback(async (notificar = true) => {
    setCargando(true);
    setErrorCarga('');
    try {
      const data = await apiClient.callModule('mod-programas-estudio', 'periodos');
      setPeriods(Array.isArray(data) ? data : []);
    } catch (e) {
      const mensaje = e?.message || 'No se pudieron cargar los periodos lectivos.';
      setErrorCarga(mensaje);
      if (notificar) error(mensaje);
    } finally {
      setCargando(false);
    }
  }, [error]);

  useEffect(() => {
    let activo = true;
    const iniciarCarga = async () => {
      await Promise.resolve();
      if (activo) await cargarPeriodos();
    };
    iniciarCarga();
    return () => { activo = false; };
  }, [cargarPeriodos]);

  const recargarPadre = useCallback(async () => {
    if (!onUpdate) return;
    try {
      await onUpdate();
    } catch (e) {
      console.error('No se pudo actualizar el dashboard académico:', e);
    }
  }, [onUpdate]);

  const periodoEditando = useMemo(
    () => periods.find((periodo) => String(periodo.id) === String(editandoId)),
    [periods, editandoId]
  );
  const relaciones = useMemo(() => resumenRelaciones(periodoEditando), [periodoEditando]);
  const hayCambios = editandoId !== null && JSON.stringify(formulario) !== JSON.stringify(formularioInicial);

  const periodosFiltrados = useMemo(() => periods.filter((periodo) => {
    const coincideEstado = filtroEstado === 'todos'
      || String(periodo.estado ?? '').toLowerCase() === filtroEstado;
    return coincideEstado && coincidePeriodo(periodo, busqueda);
  }), [periods, busqueda, filtroEstado]);

  const manejarCierre = useCallback(async () => {
    if (hayCambios) {
      const descartar = await confirmar({
        title: 'Descartar cambios',
        message: 'Tiene modificaciones sin guardar en el periodo. ¿Desea descartarlas y cerrar la gestión?',
        confirmText: 'Descartar cambios',
        cancelText: 'Seguir editando',
        type: 'warning'
      });
      if (!descartar) return;
    }
    onClose();
  }, [hayCambios, confirmar, onClose]);

  useEffect(() => {
    const overflowAnterior = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const alPulsarEscape = (evento) => {
      if (evento.key === 'Escape' && !guardando) manejarCierre();
    };
    window.addEventListener('keydown', alPulsarEscape);
    return () => {
      window.removeEventListener('keydown', alPulsarEscape);
      document.body.style.overflow = overflowAnterior;
    };
  }, [guardando, manejarCierre]);

  const cambiarCampo = (campo, valor) => {
    setErrores((anteriores) => ({ ...anteriores, [campo]: undefined }));
    setFormulario((anterior) => {
      const siguiente = { ...anterior, [campo]: valor };
      if (campo === 'codigo' && (anterior.nombre === anterior.codigo || !anterior.nombre)) {
        siguiente.nombre = valor;
      }
      return siguiente;
    });
  };

  const iniciarEdicion = (periodo) => {
    const datos = {
      codigo: periodo.codigo ?? '',
      nombre: periodo.nombre ?? periodo.codigo ?? '',
      fecha_inicio: soloFecha(periodo.fecha_inicio),
      fecha_fin: soloFecha(periodo.fecha_fin),
      fecha_fin_matricula_regular: soloFecha(periodo.fecha_fin_matricula_regular),
      fecha_fin_matricula_extemporanea: soloFecha(periodo.fecha_fin_matricula_extemporanea),
      estado: ESTADOS_PERIODO.some((opcion) => opcion.value === periodo.estado)
        ? periodo.estado
        : 'planificacion'
    };
    setEditandoId(periodo.id);
    setFormulario({ ...datos });
    setFormularioInicial({ ...datos });
    setErrores({});
  };

  const cancelarEdicion = async () => {
    if (hayCambios) {
      const descartar = await confirmar({
        title: 'Descartar cambios',
        message: 'Los cambios realizados en el periodo se perderán. ¿Desea continuar?',
        confirmText: 'Descartar cambios',
        cancelText: 'Seguir editando',
        type: 'warning'
      });
      if (!descartar) return;
    }
    setEditandoId(null);
    setFormulario({ ...FORMULARIO_VACIO });
    setFormularioInicial({ ...FORMULARIO_VACIO });
    setErrores({});
  };

  const guardar = async (evento) => {
    evento.preventDefault();
    if (guardando) return;

    const { errores: nuevosErrores, payload } = validarPeriodo(formulario, periods, editandoId);
    if (Object.keys(nuevosErrores).length > 0) {
      setErrores(nuevosErrores);
      error('Revise los campos marcados antes de continuar.');
      return;
    }
    setErrores({});

    if (
      editandoId !== null
      && relaciones.total > 0
      && normalizarCodigo(formulario.codigo) !== normalizarCodigo(periodoEditando?.codigo)
    ) {
      error(
        'No se puede cambiar el código: este periodo tiene matrículas, notas o carga lectiva vinculadas. Puede actualizar el nombre y las fechas sin afectar las relaciones.'
      );
      return;
    }

    const esEdicion = editandoId !== null;
    const aceptado = await confirmar({
      title: esEdicion ? 'Guardar cambios del periodo' : 'Registrar periodo lectivo',
      message: esEdicion
        ? `Se actualizará el periodo "${periodoEditando?.codigo}". Se conservarán sus relaciones con matrículas, notas y carga lectiva.`
        : `Se registrará el periodo "${payload.codigo}" con las fechas indicadas.`,
      confirmText: esEdicion ? 'Guardar cambios' : 'Registrar periodo',
      cancelText: 'Cancelar',
      type: relaciones.total > 0 ? 'warning' : 'default'
    });
    if (!aceptado) return;

    setGuardando(true);
    try {
      if (esEdicion) {
        await apiClient.callModule('mod-programas-estudio', `periodos/${editandoId}`, 'PUT', payload);
      } else {
        await apiClient.callModule('mod-programas-estudio', 'periodos', 'POST', payload);
      }
      success(esEdicion
        ? `Periodo "${payload.codigo}" actualizado correctamente.`
        : `Periodo "${payload.codigo}" registrado correctamente.`);
      await cargarPeriodos(false);
      await recargarPadre();
      setEditandoId(null);
      setFormulario({ ...FORMULARIO_VACIO });
      setFormularioInicial({ ...FORMULARIO_VACIO });
    } catch (e) {
      error(e?.message || (esEdicion
        ? 'No se pudieron guardar los cambios del periodo.'
        : 'No se pudo registrar el periodo.'));
    } finally {
      setGuardando(false);
    }
  };

  const cambiarEstado = async (periodo, nuevoEstado) => {
    if (String(nuevoEstado) === String(periodo.estado)) return;
    if (!ESTADOS_PERIODO.some((opcion) => opcion.value === nuevoEstado)) {
      error('El estado seleccionado no es válido.');
      return;
    }
    const relacionesPeriodo = resumenRelaciones(periodo);
    const aceptado = await confirmar({
      title: 'Cambiar estado del periodo',
      message: `El periodo "${periodo.codigo}" pasará de "${periodo.estado}" a "${nuevoEstado}".`
        + (relacionesPeriodo.total > 0
          ? ` Tiene ${relacionesPeriodo.partes.join(', ')} vinculadas; verifique que el nuevo estado sea coherente.`
          : ''),
      confirmText: 'Cambiar estado',
      type: relacionesPeriodo.total > 0 ? 'warning' : 'default'
    });
    if (!aceptado) return;

    setCambiandoEstadoId(periodo.id);
    try {
      await apiClient.callModule(
        'mod-programas-estudio',
        `periodos/${periodo.id}/estado?estado=${encodeURIComponent(nuevoEstado)}`,
        'PUT'
      );
      success(`Estado del periodo "${periodo.codigo}" actualizado a "${nuevoEstado}".`);
      await cargarPeriodos(false);
      await recargarPadre();
    } catch (e) {
      error(e?.message || 'No se pudo actualizar el estado del periodo.');
    } finally {
      setCambiandoEstadoId(null);
    }
  };

  const contenido = (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center p-3 sm:p-4 bg-slate-950/40 backdrop-blur-sm animate-fade-in"
      onMouseDown={(evento) => {
        if (evento.target === evento.currentTarget) manejarCierre();
      }}
    >
      <div
        className="bg-white rounded-2xl border border-slate-200/90 shadow-2xl w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="titulo-gestion-periodos"
      >
        <div className="flex justify-between items-center px-6 py-4 border-b border-slate-100 shrink-0">
          <div>
            <h5 id="titulo-gestion-periodos" className="font-bold text-base text-slate-900 tracking-tight">
              Periodos y Calendario Académico
            </h5>
            <p className="text-xs text-slate-400">
              edición segura de cronogramas y ventanas de matrícula regular/extemporánea
            </p>
          </div>
          <button
            type="button"
            onClick={manejarCierre}
            className="text-slate-400 hover:text-slate-700 p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col md:flex-row flex-grow min-h-0 overflow-hidden">
          <div className="w-full md:w-5/12 p-6 bg-slate-50/60 border-r border-slate-100 overflow-y-auto">
            <div className="flex items-center justify-between gap-2 mb-4">
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                {editandoId !== null ? 'Editar Periodo' : 'Crear Periodo'}
              </span>
              {editandoId !== null && (
                <span className="text-[10px] font-semibold text-slate-500 bg-white border border-slate-200 px-2 py-0.5 rounded-full">
                  {periodoEditando?.codigo || ''}
                </span>
              )}
            </div>

            {editandoId !== null && relaciones.total > 0 && (
              <div className="mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-[11px] text-amber-900 leading-relaxed">
                <div className="flex items-start gap-2">
                  <ShieldCheck size={15} className="shrink-0 mt-0.5 text-amber-600" />
                  <div>
                    <p className="font-bold mb-0.5">Periodo con información vinculada</p>
                    <p>{relaciones.partes.join(' · ')}.</p>
                    <p className="mt-1 font-semibold">
                      El código permanece bloqueado para no afectar otros módulos. El nombre, las fechas y el estado sí se pueden ajustar.
                    </p>
                  </div>
                </div>
              </div>
            )}

            <form onSubmit={guardar} className="space-y-3.5" noValidate>
              <CampoFormulario
                id="periodo-codigo"
                etiqueta="Código del Periodo"
                valor={formulario.codigo}
                onChange={(valor) => cambiarCampo('codigo', normalizarCodigo(valor))}
                error={errores.codigo}
                deshabilitado={guardando || (editandoId !== null && relaciones.total > 0)}
                placeholder="Ej. 2026-I"
                monoespacio
              />
              <CampoFormulario
                id="periodo-nombre"
                etiqueta="Nombre del Periodo"
                valor={formulario.nombre}
                onChange={(valor) => cambiarCampo('nombre', valor)}
                error={errores.nombre}
                deshabilitado={guardando}
                placeholder="Ej. Primer Semestre 2026"
              />

              <div className="grid grid-cols-2 gap-2.5">
                <CampoFormulario
                  id="periodo-inicio"
                  etiqueta="Fecha Inicio"
                  tipo="date"
                  valor={formulario.fecha_inicio}
                  onChange={(valor) => cambiarCampo('fecha_inicio', valor)}
                  error={errores.fecha_inicio}
                  deshabilitado={guardando}
                />
                <CampoFormulario
                  id="periodo-fin"
                  etiqueta="Fecha Fin"
                  tipo="date"
                  valor={formulario.fecha_fin}
                  onChange={(valor) => cambiarCampo('fecha_fin', valor)}
                  error={errores.fecha_fin}
                  deshabilitado={guardando}
                />
              </div>

              <CampoFormulario
                id="periodo-regular"
                etiqueta="Cierre Matrícula Regular"
                tipo="date"
                valor={formulario.fecha_fin_matricula_regular}
                onChange={(valor) => cambiarCampo('fecha_fin_matricula_regular', valor)}
                error={errores.fecha_fin_matricula_regular}
                deshabilitado={guardando}
              />
              <CampoFormulario
                id="periodo-extemporanea"
                etiqueta="Cierre Matrícula Extemporánea"
                tipo="date"
                valor={formulario.fecha_fin_matricula_extemporanea}
                onChange={(valor) => cambiarCampo('fecha_fin_matricula_extemporanea', valor)}
                error={errores.fecha_fin_matricula_extemporanea}
                deshabilitado={guardando}
              />

              <div>
                <label htmlFor="periodo-estado" className="block text-[11px] font-semibold text-slate-600 uppercase tracking-wider mb-1">
                  Estado
                </label>
                <select
                  id="periodo-estado"
                  className={`${inputBase} border-slate-200 ${errores.estado ? 'border-rose-300' : ''}`}
                  value={formulario.estado}
                  onChange={(evento) => cambiarCampo('estado', evento.target.value)}
                  disabled={guardando}
                >
                  {ESTADOS_PERIODO.map((opcion) => (
                    <option key={opcion.value} value={opcion.value}>{opcion.label}</option>
                  ))}
                </select>
                {errores.estado && <p className="mt-1 text-[11px] font-medium text-rose-600">{errores.estado}</p>}
              </div>

              <div className="flex gap-2 pt-1">
                <button
                  type="submit"
                  className="flex-1 py-2.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-semibold shadow-sm transition-all flex items-center justify-center gap-1.5 disabled:opacity-60"
                  disabled={guardando}
                  data-testid="periodo-guardar"
                >
                  {guardando ? (
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : editandoId !== null ? (
                    <><Save size={15} /><span>Guardar Cambios</span></>
                  ) : (
                    <><Plus size={15} /><span>Registrar Periodo</span></>
                  )}
                </button>
                {editandoId !== null && (
                  <button
                    type="button"
                    onClick={cancelarEdicion}
                    disabled={guardando}
                    className="px-3 py-2.5 bg-white hover:bg-slate-100 text-slate-600 rounded-xl text-xs font-semibold border border-slate-200 transition-all flex items-center gap-1.5 disabled:opacity-60"
                  >
                    <RotateCcw size={14} />
                    Cancelar
                  </button>
                )}
              </div>
            </form>

            <div className="mt-5 p-3.5 rounded-xl bg-slate-100/70 border border-slate-200/80 text-[11px] text-slate-600 leading-relaxed">
              <span className="font-bold text-slate-800 block mb-1">Información de Ciclos:</span>
              El estado <strong>Matrícula Abierta</strong> habilita inscripciones en el portal. Al pasar a <strong>En Curso</strong>, el motor restringe la matrícula regular y habilita el registro de notas.
            </div>
          </div>

          <div className="w-full md:w-7/12 p-6 overflow-y-auto">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mb-4">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Historial de Periodos</span>
                <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                  {periodosFiltrados.length}/{periods.length}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative flex-1 sm:w-56">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="search"
                    value={busqueda}
                    onChange={(evento) => setBusqueda(evento.target.value)}
                    placeholder="Buscar periodo..."
                    aria-label="Buscar periodos"
                    className="w-full pl-8 pr-2 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                  />
                </div>
                <select
                  value={filtroEstado}
                  onChange={(evento) => setFiltroEstado(evento.target.value)}
                  aria-label="Filtrar por estado"
                  className="py-1.5 px-2 bg-white border border-slate-200 rounded-lg text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/20"
                >
                  <option value="todos">Todos</option>
                  {ESTADOS_PERIODO.map((opcion) => (
                    <option key={opcion.value} value={opcion.value}>{opcion.label}</option>
                  ))}
                </select>
              </div>
            </div>

            {errorCarga ? (
              <div className="text-center py-12 border border-rose-200 bg-rose-50/50 rounded-xl">
                <AlertTriangle size={22} className="mx-auto mb-2 text-rose-500" />
                <p className="text-rose-700 text-xs font-semibold">{errorCarga}</p>
                <button
                  type="button"
                  onClick={() => cargarPeriodos()}
                  className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 rounded-lg text-xs font-semibold"
                >
                  <RefreshCw size={13} /> Reintentar
                </button>
              </div>
            ) : cargando ? (
              <div className="flex flex-col items-center justify-center py-16">
                <div className="w-6 h-6 border-2 border-slate-900 border-t-transparent rounded-full animate-spin mb-2" />
                <p className="text-slate-400 text-xs">Cargando cronogramas...</p>
              </div>
            ) : periods.length === 0 ? (
              <div className="text-center py-12 border border-dashed border-slate-200 rounded-xl">
                <div className="w-10 h-10 mx-auto mb-2 rounded-xl bg-slate-100 text-slate-400 flex items-center justify-center">
                  <Calendar size={20} />
                </div>
                <p className="text-slate-400 text-xs">No hay periodos registrados aún.</p>
              </div>
            ) : periodosFiltrados.length === 0 ? (
              <div className="text-center py-12 border border-dashed border-slate-200 rounded-xl">
                <Search size={20} className="mx-auto mb-2 text-slate-300" />
                <p className="text-slate-500 text-xs font-semibold">No hay periodos que coincidan con la búsqueda.</p>
                <button
                  type="button"
                  onClick={() => { setBusqueda(''); setFiltroEstado('todos'); }}
                  className="mt-2 text-[11px] font-semibold text-primary hover:underline"
                >
                  Limpiar filtros
                </button>
              </div>
            ) : (
              <div className="space-y-2.5">
                {periodosFiltrados.map((periodo) => {
                  const vinculos = resumenRelaciones(periodo);
                  const esEditando = String(periodo.id) === String(editandoId);
                  return (
                    <div
                      key={periodo.id}
                      className={`p-3.5 rounded-xl border hover:shadow-sm transition-all bg-white ${esEditando ? 'border-primary ring-2 ring-primary/10' : 'border-slate-200/80 hover:border-slate-300'}`}
                    >
                      <div className="flex justify-between items-start gap-2">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-10 h-10 shrink-0 rounded-xl bg-slate-100 text-slate-800 font-bold text-sm flex items-center justify-center border border-slate-200/60 font-mono">
                            {String(periodo.codigo ?? '—').split('-')[1] || String(periodo.codigo ?? '—').slice(0, 3)}
                          </div>
                          <div className="min-w-0">
                            <h4 className="font-bold text-sm text-slate-900 tracking-tight truncate">{periodo.codigo}</h4>
                            {periodo.nombre && periodo.nombre !== periodo.codigo && (
                              <p className="text-[11px] text-slate-500 truncate">{periodo.nombre}</p>
                            )}
                            <div className="text-[11px] text-slate-400 flex items-center gap-1.5 mt-0.5 flex-wrap">
                              <Clock size={12} className="text-slate-400 shrink-0" />
                              <span>{formatearFecha(periodo.fecha_inicio)}</span>
                              <ArrowRight size={11} />
                              <span>{formatearFecha(periodo.fecha_fin)}</span>
                            </div>
                          </div>
                        </div>

                        <div className="flex flex-col items-end gap-2 shrink-0">
                          <BadgeEstado estado={periodo.estado} />
                          <div className="flex items-center gap-1.5">
                            <label
                              htmlFor={`estado-periodo-${periodo.id}`}
                              className="text-[10px] text-slate-400"
                            >
                              Estado:
                            </label>
                            <select
                              id={`estado-periodo-${periodo.id}`}
                              className="text-[11px] font-semibold text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg px-2 py-0.5 cursor-pointer outline-none transition-colors disabled:opacity-60"
                              value={periodo.estado}
                              onChange={(evento) => cambiarEstado(periodo, evento.target.value)}
                              disabled={cambiandoEstadoId === periodo.id}
                            >
                              {ESTADOS_PERIODO.map((opcion) => (
                                <option key={opcion.value} value={opcion.value}>{opcion.label}</option>
                              ))}
                              {!ESTADOS_PERIODO.some((opcion) => opcion.value === periodo.estado) && (
                                <option value={periodo.estado}>{periodo.estado}</option>
                              )}
                            </select>
                            <button
                              type="button"
                              onClick={() => iniciarEdicion(periodo)}
                              disabled={guardando}
                              data-testid={`editar-periodo-${periodo.id}`}
                              aria-label={`Editar periodo ${periodo.codigo}`}
                              className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 rounded-lg transition-colors disabled:opacity-60"
                            >
                              <Edit3 size={12} />
                              Editar
                            </button>
                          </div>
                        </div>
                      </div>

                      {vinculos.total > 0 && (
                        <div className="mt-2 pt-2 border-t border-slate-100 flex items-start gap-1.5 text-[10px] text-amber-700">
                          <Info size={12} className="shrink-0 mt-0.5" />
                          <span>Vinculado a: {vinculos.partes.join(' · ')}. Los cambios conservan estas relaciones.</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  if (typeof document === 'undefined' || !document.body) return null;
  return createPortal(contenido, document.body);
}

export { BadgeEstado };
