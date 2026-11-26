/**
 * Utilidades puras para el formulario de periodos lectivos.
 * Se mantienen sin dependencias de React para poder probarlas de forma aislada.
 */

export const ESTADOS_PERIODO = [
  { value: 'planificacion', label: 'Planificación' },
  { value: 'matricula_abierta', label: 'Matrícula Abierta' },
  { value: 'en_curso', label: 'En Curso' },
  { value: 'historico', label: 'Histórico' },
  { value: 'cerrado', label: 'Cerrado' }
];

export const CAMPOS_RELACION = [
  { key: 'matriculas', label: 'matrículas' },
  { key: 'notas', label: 'notas registradas' },
  { key: 'carga_lectiva', label: 'cargas lectivas' },
  { key: 'planes_trabajo', label: 'planes de trabajo' },
  { key: 'tutorias', label: 'tutorías' },
  { key: 'horarios', label: 'horarios' }
];

export const FORMULARIO_VACIO = {
  codigo: '',
  nombre: '',
  fecha_inicio: '',
  fecha_fin: '',
  fecha_fin_matricula_regular: '',
  fecha_fin_matricula_extemporanea: '',
  estado: 'planificacion'
};

export function normalizarTexto(valor = '') {
  return String(valor ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ');
}

export function normalizarCodigo(valor = '') {
  return String(valor ?? '').trim().toUpperCase();
}

function parsearFecha(valor) {
  const coincidencia = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(valor ?? ''));
  if (!coincidencia) return null;
  const fecha = new Date(
    Number(coincidencia[1]),
    Number(coincidencia[2]) - 1,
    Number(coincidencia[3])
  );
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

/** Formatea fechas sin desplazar el día por la zona horaria del navegador. */
export function formatearFecha(valor) {
  const fecha = parsearFecha(valor);
  if (!fecha) return '—';
  return fecha.toLocaleDateString('es-PE', {
    day: '2-digit',
    month: 'short',
    year: 'numeric'
  });
}

export function resumenRelaciones(periodo) {
  const relaciones = periodo?.relaciones || {};
  const partes = CAMPOS_RELACION
    .filter(({ key }) => Number(relaciones[key]) > 0)
    .map(({ key, label }) => `${relaciones[key]} ${label}`);

  const totalCalculado = CAMPOS_RELACION.reduce(
    (suma, { key }) => suma + (Number(relaciones[key]) || 0),
    0
  );

  return {
    partes,
    total: Number(relaciones.total) || totalCalculado
  };
}

export function coincidePeriodo(periodo, busqueda) {
  const terminos = normalizarTexto(busqueda).split(' ').filter(Boolean);
  if (terminos.length === 0) return true;

  const contenido = normalizarTexto([
    periodo?.codigo,
    periodo?.nombre,
    periodo?.estado,
    formatearFecha(periodo?.fecha_inicio),
    formatearFecha(periodo?.fecha_fin)
  ].join(' '));

  return terminos.every((termino) => contenido.includes(termino));
}

/**
 * Valida el formulario y construye el payload que espera el backend.
 * Devuelve `{ errores, payload }`; `payload` es válido sólo si `errores` está vacío.
 */
export function validarPeriodo(formulario, periodos = [], idActual = null) {
  const errores = {};
  const codigo = normalizarCodigo(formulario?.codigo);
  const nombre = String(formulario?.nombre ?? '').trim();
  const estado = String(formulario?.estado ?? '');

  if (!codigo) {
    errores.codigo = 'Ingrese el código del periodo.';
  } else if (!/^[A-Z0-9-]{3,20}$/.test(codigo)) {
    errores.codigo = 'Use de 3 a 20 caracteres: letras, números y guiones.';
  } else if (periodos.some((periodo) => (
    String(periodo?.id) !== String(idActual) && normalizarCodigo(periodo?.codigo) === codigo
  ))) {
    errores.codigo = `Ya existe un periodo con el código "${codigo}".`;
  }

  if (nombre.length > 120) {
    errores.nombre = 'El nombre no puede superar los 120 caracteres.';
  }

  const inicio = parsearFecha(formulario?.fecha_inicio);
  const fin = parsearFecha(formulario?.fecha_fin);
  const regular = parsearFecha(formulario?.fecha_fin_matricula_regular);
  const extemporanea = parsearFecha(formulario?.fecha_fin_matricula_extemporanea);

  if (!inicio) errores.fecha_inicio = 'Seleccione la fecha de inicio.';
  if (!fin) errores.fecha_fin = 'Seleccione la fecha de fin.';
  if (!regular) errores.fecha_fin_matricula_regular = 'Seleccione el cierre de matrícula regular.';
  if (!extemporanea) errores.fecha_fin_matricula_extemporanea = 'Seleccione el cierre de matrícula extemporánea.';

  if (inicio && fin && inicio >= fin) {
    errores.fecha_fin = 'La fecha de fin debe ser posterior a la fecha de inicio.';
  }
  if (inicio && regular && (regular < inicio || (fin && regular > fin))) {
    errores.fecha_fin_matricula_regular = 'El cierre regular debe estar dentro del periodo lectivo.';
  }
  if (regular && extemporanea && extemporanea < regular) {
    errores.fecha_fin_matricula_extemporanea = 'El cierre extemporáneo no puede ser anterior al cierre regular.';
  }
  if (fin && extemporanea && extemporanea > fin) {
    errores.fecha_fin_matricula_extemporanea = 'El cierre extemporáneo no puede superar la fecha de fin.';
  }

  if (!ESTADOS_PERIODO.some((opcion) => opcion.value === estado)) {
    errores.estado = 'Seleccione un estado válido.';
  }

  const payload = {
    codigo,
    nombre: nombre || codigo,
    fecha_inicio: formulario?.fecha_inicio || '',
    fecha_fin: formulario?.fecha_fin || '',
    fecha_fin_matricula_regular: formulario?.fecha_fin_matricula_regular || '',
    fecha_fin_matricula_extemporanea: formulario?.fecha_fin_matricula_extemporanea || '',
    estado
  };

  return { errores, payload };
}
