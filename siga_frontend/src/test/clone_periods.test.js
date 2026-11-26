import { describe, it, expect } from 'vitest';
import { obtenerPeriodosOrigen, etiquetaPeriodo } from '../modules/academic/clonePeriods';

const periodos = [
  { id: 1, codigo: '2025-II', fecha_inicio: '2025-08-01T00:00:00', estado: 'historico' },
  { id: 2, codigo: '2026-I', fecha_inicio: '2026-01-05T00:00:00', estado: 'matricula_abierta' },
  { id: 3, codigo: '2026-II', fecha_inicio: '2026-08-03T00:00:00', estado: 'planificacion' }
];

describe('obtenerPeriodosOrigen', () => {
  it('solo devuelve periodos anteriores al periodo destino y los ordena del más reciente al más antiguo', () => {
    const result = obtenerPeriodosOrigen(periodos, '3');

    expect(result.map((p) => p.codigo)).toEqual(['2026-I', '2025-II']);
  });

  it('excluye el periodo destino aunque sea el único registrado', () => {
    const result = obtenerPeriodosOrigen([periodos[1]], 2);

    expect(result).toEqual([]);
  });

  it('no excluye periodos sin fecha válida para no ocultar datos incompletos', () => {
    const conFechaInvalida = [
      { id: 1, codigo: 'SIN-FECHA', fecha_inicio: null },
      periodos[1]
    ];

    const result = obtenerPeriodosOrigen(conFechaInvalida, '2');

    expect(result.map((p) => p.codigo)).toEqual(['SIN-FECHA']);
  });

  it('acepta ids numéricos o en texto para el periodo destino', () => {
    expect(obtenerPeriodosOrigen(periodos, 2).map((p) => p.id)).toEqual([1]);
    expect(obtenerPeriodosOrigen(periodos, '2').map((p) => p.id)).toEqual([1]);
  });
});

describe('etiquetaPeriodo', () => {
  it('usa el código y el estado cuando están disponibles', () => {
    expect(etiquetaPeriodo(periodos[1])).toBe('2026-I (matricula_abierta)');
  });

  it('tiene un fallback estable cuando faltan datos', () => {
    expect(etiquetaPeriodo({ id: 9 })).toBe('Periodo #9');
  });
});
