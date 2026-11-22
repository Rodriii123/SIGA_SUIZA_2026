import { describe, expect, it } from 'vitest';
import * as tupaCatalog from '../modules/finances/tupaCatalog';
import { nombreProgramaEstudiante } from '../core/api/programas';

const programas = [
  { id: 6, nombre: 'Mecatrónica Automotriz', codigo: 'MEC' },
  { id: 15, nombre: 'Desarrollo de Sistemas de Información', codigo: 'DSI' },
];

describe('Finanzas resuelve la carrera desde datos reales', () => {
  it('un estudiante de DSI nunca aparece como Mecatrónica', () => {
    const estudiante = {
      programa_id: 15,
      programa_nombre: 'Desarrollo de Sistemas de Información',
      programa_codigo: 'DSI',
    };

    const nombre = nombreProgramaEstudiante(estudiante, programas);

    expect(nombre).toBe('Desarrollo de Sistemas de Información');
    expect(nombre).not.toBe('Mecatrónica Automotriz');
  });

  it('si la API no trae programa_nombre, usa el catálogo por id real', () => {
    expect(nombreProgramaEstudiante({ programa_id: 15 }, programas))
      .toBe('Desarrollo de Sistemas de Información');
  });

  it('el catálogo de Finanzas ya no exporta un mapa fijo de carreras', () => {
    expect('CAREERS_MAP' in tupaCatalog).toBe(false);
  });
});
