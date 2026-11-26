/**
 * Utilidades para el flujo "Clonar carga lectiva del periodo anterior".
 *
 * El periodo de destino siempre es el periodo actualmente seleccionado. El
 * origen debe ser un periodo distinto y anterior; nunca se ofrecen periodos
 * futuros ni el propio periodo de destino.
 */

function periodoStartTime(periodo) {
  const raw = periodo?.fecha_inicio ?? periodo?.fechaInicio;
  if (!raw) return null;
  const time = new Date(raw).getTime();
  return Number.isNaN(time) ? null : time;
}

function sortByStartDesc(a, b) {
  const ta = periodoStartTime(a);
  const tb = periodoStartTime(b);
  if (ta !== null && tb !== null) return tb - ta;
  if (ta !== null) return -1;
  if (tb !== null) return 1;
  return String(b?.codigo || b?.nombre || '').localeCompare(
    String(a?.codigo || a?.nombre || '')
  );
}

/**
 * Devuelve los periodos que pueden usarse como origen para clonar carga
 * lectiva hacia `selectedPeriodId`.
 *
 * - Excluye el periodo de destino.
 * - Si el destino tiene fecha de inicio válida, excluye periodos posteriores.
 * - Ordena del más reciente al más antiguo.
 */
export function obtenerPeriodosOrigen(periods = [], selectedPeriodId) {
  if (!Array.isArray(periods) || !periods.length) return [];

  const targetId = selectedPeriodId == null ? null : String(selectedPeriodId);
  const target = periods.find((p) => String(p?.id) === targetId);
  const targetTime = periodoStartTime(target);

  return periods
    .filter((p) => String(p?.id) !== targetId)
    .filter((p) => {
      if (targetTime === null) return true;
      const startTime = periodoStartTime(p);
      // Si un periodo no tiene fecha válida no lo descartamos: preferimos
      // mostrarlo antes que ocultar datos incompletos de la base.
      return startTime === null || startTime < targetTime;
    })
    .sort(sortByStartDesc);
}

export function etiquetaPeriodo(periodo) {
  const nombre = periodo?.codigo || periodo?.nombre || `Periodo #${periodo?.id}`;
  return periodo?.estado ? `${nombre} (${periodo.estado})` : nombre;
}
