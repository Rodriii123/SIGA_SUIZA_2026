import { describe, it, expect } from 'vitest';
import {
  coincidePeriodo,
  formatearFecha,
  normalizarCodigo,
  resumenRelaciones,
  validarPeriodo
} from '../modules/academic/periodValidation';

const formularioValido = {
  codigo: '2027-i',
  fecha_inicio: '2027-01-10',
  fecha_fin: '2027-06-20',
  fecha_fin_matricula_regular: '2027-02-20',
  fecha_fin_matricula_extemporanea: '2027-03-05',
  estado: 'planificacion'
};

describe('validación del formulario de periodos', () => {
  it('normaliza el código y construye un payload coherente', () => {
    const { errores, payload } = validarPeriodo(formularioValido);
    expect(errores).toEqual({});
    expect(payload.codigo).toBe('2027-I');
    expect(payload.estado).toBe('planificacion');
    expect(payload).not.toHaveProperty('nombre');
  });

  it('no incluye el campo nombre en el payload', () => {
    const { payload } = validarPeriodo(formularioValido);
    expect(Object.keys(payload)).toEqual([
      'codigo',
      'fecha_inicio',
      'fecha_fin',
      'fecha_fin_matricula_regular',
      'fecha_fin_matricula_extemporanea',
      'estado'
    ]);
  });

  it('rechaza códigos duplicados excepto el periodo que se está editando', () => {
    const periodos = [{ id: 9, codigo: '2027-II' }];
    const duplicado = validarPeriodo({ ...formularioValido, codigo: '2027-ii' }, periodos, 1);
    expect(duplicado.errores.codigo).toMatch(/Ya existe un periodo/);

    const mismoPeriodo = validarPeriodo(formularioValido, [{ id: 1, codigo: '2027-I' }], 1);
    expect(mismoPeriodo.errores.codigo).toBeUndefined();
  });

  it('rechaza fechas invertidas y ventanas de matrícula incoherentes', () => {
    expect(validarPeriodo({ ...formularioValido, fecha_fin: '2027-01-01' }).errores.fecha_fin)
      .toMatch(/posterior/);
    expect(validarPeriodo({ ...formularioValido, fecha_fin_matricula_regular: '2026-12-01' }).errores.fecha_fin_matricula_regular)
      .toMatch(/dentro del periodo/);
    expect(validarPeriodo({ ...formularioValido, fecha_fin_matricula_extemporanea: '2027-02-01' }).errores.fecha_fin_matricula_extemporanea)
      .toMatch(/anterior al cierre regular/);
    expect(validarPeriodo({ ...formularioValido, fecha_fin_matricula_extemporanea: '2027-07-01' }).errores.fecha_fin_matricula_extemporanea)
      .toMatch(/fecha de fin/);
  });

  it('rechaza estados no reconocidos', () => {
    const { errores } = validarPeriodo({ ...formularioValido, estado: 'inventado' });
    expect(errores.estado).toMatch(/estado válido/);
  });

  it('formatea fechas sin desplazar el día por zona horaria', () => {
    expect(formatearFecha('2026-01-01T00:00:00')).toContain('01');
    expect(formatearFecha('2026-01-01T00:00:00')).toContain('2026');
    expect(formatearFecha(null)).toBe('—');
  });

  it('busca por código y estado sin distinguir tildes', () => {
    const periodo = { codigo: '2026-I', estado: 'matricula_abierta' };
    expect(coincidePeriodo(periodo, 'matricula abierta')).toBe(true);
    expect(coincidePeriodo(periodo, '2026')).toBe(true);
    expect(coincidePeriodo(periodo, 'historico')).toBe(false);
  });

  it('resume las relaciones vinculadas al periodo', () => {
    const resumen = resumenRelaciones({
      relaciones: { matriculas: 3, notas: 0, carga_lectiva: 2, total: 5 }
    });
    expect(resumen.total).toBe(5);
    expect(resumen.partes).toEqual(['3 matrículas', '2 cargas lectivas']);
  });

  it('normaliza código con espacios y minúsculas', () => {
    expect(normalizarCodigo('  2026-ii  ')).toBe('2026-II');
  });
});
