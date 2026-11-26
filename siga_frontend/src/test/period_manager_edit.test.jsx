import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import { PeriodManager } from '../modules/academic/PeriodManager';
import { apiClient } from '../core/api/client';
import { ToastProvider } from '../core/ui/ToastContext';
import { ConfirmProvider } from '../core/ui/ConfirmModal';

vi.mock('../core/api/client', () => ({
  apiClient: {
    callModule: vi.fn(),
    request: vi.fn()
  }
}));

// `nombre` simula datos legados de PostgreSQL: no debe aparecer en la interfaz.
const periodosBase = [
  {
    id: 1,
    codigo: '2026-I',
    nombre: 'Primer Semestre 2026',
    estado: 'en_curso',
    fecha_inicio: '2026-01-05T00:00:00',
    fecha_fin: '2026-06-20T00:00:00',
    fecha_fin_matricula_regular: '2026-02-20T00:00:00',
    fecha_fin_matricula_extemporanea: '2026-03-05T00:00:00',
    relaciones: { matriculas: 12, notas: 4, carga_lectiva: 6, total: 22 }
  },
  {
    id: 2,
    codigo: '2026-II',
    nombre: 'Segundo Semestre 2026',
    estado: 'planificacion',
    fecha_inicio: '2026-08-03T00:00:00',
    fecha_fin: '2026-12-18T00:00:00',
    fecha_fin_matricula_regular: '2026-09-03T00:00:00',
    fecha_fin_matricula_extemporanea: '2026-09-18T00:00:00',
    relaciones: { matriculas: 0, notas: 0, carga_lectiva: 0, total: 0 }
  }
];

function renderManager(onUpdate = vi.fn()) {
  return render(
    <ToastProvider>
      <ConfirmProvider>
        <PeriodManager onClose={vi.fn()} onUpdate={onUpdate} />
      </ConfirmProvider>
    </ToastProvider>
  );
}

describe('PeriodManager - edición segura de periodos lectivos', () => {
  let periodos;

  beforeEach(() => {
    vi.clearAllMocks();
    periodos = periodosBase.map((periodo) => ({
      ...periodo,
      relaciones: { ...periodo.relaciones }
    }));
    apiClient.callModule.mockImplementation(async (modulo, endpoint, metodo = 'GET', datos) => {
      if (metodo === 'GET') return periodos;
      if (metodo === 'PUT' && endpoint.includes('/estado')) return periodos[0];
      if (metodo === 'PUT') {
        const id = Number(endpoint.split('/').pop());
        periodos = periodos.map((periodo) => (
          periodo.id === id ? { ...periodo, ...datos } : periodo
        ));
        return periodos.find((periodo) => periodo.id === id);
      }
      if (metodo === 'POST') return { ...datos, id: 99 };
      return [];
    });
  });

  it('muestra un botón Editar, sólo el código en la lista y permite buscar/filtrar', async () => {
    renderManager();

    expect(await screen.findByText('2026-I')).toBeInTheDocument();
    expect(screen.getByTestId('editar-periodo-1')).toBeInTheDocument();
    expect(screen.getByTestId('editar-periodo-2')).toBeInTheDocument();
    expect(screen.queryByText('Primer Semestre 2026')).not.toBeInTheDocument();
    expect(screen.queryByText('Segundo Semestre 2026')).not.toBeInTheDocument();
    expect(screen.getByText(/Vinculado a: 12 matrículas/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Buscar periodos'), { target: { value: '2026-II' } });
    expect(screen.queryByText('2026-I')).not.toBeInTheDocument();
    expect(screen.getByText('2026-II')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Buscar periodos'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Filtrar por estado'), { target: { value: 'en_curso' } });
    expect(screen.getByText('2026-I')).toBeInTheDocument();
    expect(screen.queryByText('2026-II')).not.toBeInTheDocument();
  });

  it('precarga los campos originales, oculta el nombre y guarda cambios con confirmación', async () => {
    const onUpdate = vi.fn();
    renderManager(onUpdate);

    fireEvent.click(await screen.findByTestId('editar-periodo-1'));

    expect(screen.getByLabelText('Código del Periodo')).toHaveValue('2026-I');
    expect(screen.queryByLabelText('Nombre del Periodo')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Fecha Inicio')).toHaveValue('2026-01-05');
    expect(screen.getByLabelText('Fecha Fin')).toHaveValue('2026-06-20');
    expect(screen.getByLabelText('Cierre Matrícula Regular')).toHaveValue('2026-02-20');
    expect(screen.getByLabelText('Cierre Matrícula Extemporánea')).toHaveValue('2026-03-05');
    expect(screen.getByLabelText('Estado')).toHaveValue('en_curso');
    expect(screen.getByText(/El código permanece bloqueado/)).toBeInTheDocument();
    expect(screen.getByLabelText('Código del Periodo')).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Fecha Fin'), { target: { value: '2026-06-25' } });
    fireEvent.click(screen.getByTestId('periodo-guardar'));

    const confirmacion = await screen.findByTestId('confirm-modal');
    expect(within(confirmacion).getByText(/Se actualizará el periodo/)).toBeInTheDocument();
    fireEvent.click(within(confirmacion).getByTestId('confirm-modal-ok'));

    await waitFor(() => {
      const llamada = apiClient.callModule.mock.calls.find(
        ([, endpoint, metodo]) => metodo === 'PUT' && endpoint === 'periodos/1'
      );
      expect(llamada).toBeTruthy();
      expect(llamada[3]).toMatchObject({
        codigo: '2026-I',
        fecha_fin: '2026-06-25',
        estado: 'en_curso'
      });
      expect(llamada[3]).not.toHaveProperty('nombre');
    });

    expect(await screen.findByTestId('toast-success')).toBeInTheDocument();
    await waitFor(() => expect(onUpdate).toHaveBeenCalled());
    await waitFor(() => {
      expect(apiClient.callModule.mock.calls.filter(([, , metodo]) => !metodo || metodo === 'GET').length)
        .toBeGreaterThan(1);
    });
  });

  it('crea un periodo con los campos originales y sin campo nombre', async () => {
    renderManager();

    fireEvent.change(screen.getByLabelText('Código del Periodo'), { target: { value: '2027-i' } });
    fireEvent.change(screen.getByLabelText('Fecha Inicio'), { target: { value: '2027-01-10' } });
    fireEvent.change(screen.getByLabelText('Fecha Fin'), { target: { value: '2027-06-20' } });
    fireEvent.change(screen.getByLabelText('Cierre Matrícula Regular'), { target: { value: '2027-02-20' } });
    fireEvent.change(screen.getByLabelText('Cierre Matrícula Extemporánea'), { target: { value: '2027-03-05' } });
    fireEvent.click(screen.getByTestId('periodo-guardar'));

    const confirmacion = await screen.findByTestId('confirm-modal');
    fireEvent.click(within(confirmacion).getByTestId('confirm-modal-ok'));

    await waitFor(() => {
      const llamada = apiClient.callModule.mock.calls.find(
        ([, , metodo]) => metodo === 'POST'
      );
      expect(llamada).toBeTruthy();
      expect(llamada[3]).toEqual({
        codigo: '2027-I',
        fecha_inicio: '2027-01-10',
        fecha_fin: '2027-06-20',
        fecha_fin_matricula_regular: '2027-02-20',
        fecha_fin_matricula_extemporanea: '2027-03-05',
        estado: 'planificacion'
      });
    });
    expect(await screen.findByTestId('toast-success')).toBeInTheDocument();
  });

  it('permite corregir el código sin relaciones y conserva el cambio tras recargar', async () => {
    const primera = renderManager();
    fireEvent.click(await screen.findByTestId('editar-periodo-2'));

    const codigo = screen.getByLabelText('Código del Periodo');
    expect(codigo).not.toBeDisabled();
    fireEvent.change(codigo, { target: { value: '2027-II' } });
    fireEvent.click(screen.getByTestId('periodo-guardar'));
    fireEvent.click((await screen.findByTestId('confirm-modal')).querySelector('[data-testid="confirm-modal-ok"]'));

    await waitFor(() => expect(periodos[1].codigo).toBe('2027-II'));
    primera.unmount();

    renderManager();
    expect(await screen.findByText('2027-II')).toBeInTheDocument();
    expect(screen.queryByText('2026-II')).not.toBeInTheDocument();
  });

  it('rechaza un código duplicado sin enviar la petición', async () => {
    renderManager();
    fireEvent.click(await screen.findByTestId('editar-periodo-2'));
    fireEvent.change(screen.getByLabelText('Código del Periodo'), { target: { value: '2026-I' } });
    fireEvent.click(screen.getByTestId('periodo-guardar'));

    expect(await screen.findByText(/Ya existe un periodo con el código "2026-I"/)).toBeInTheDocument();
    expect(await screen.findByTestId('toast-error')).toBeInTheDocument();
    expect(apiClient.callModule.mock.calls.some(([, , metodo]) => metodo === 'PUT')).toBe(false);
  });

  it('cancela la edición con confirmación sin guardar', async () => {
    renderManager();
    fireEvent.click(await screen.findByTestId('editar-periodo-2'));
    fireEvent.change(screen.getByLabelText('Código del Periodo'), { target: { value: '2026-IIB' } });
    fireEvent.click(screen.getByText('Cancelar'));

    const confirmacion = await screen.findByTestId('confirm-modal');
    fireEvent.click(within(confirmacion).getByTestId('confirm-modal-ok'));

    await waitFor(() => {
      expect(screen.getByLabelText('Código del Periodo')).toHaveValue('');
      expect(screen.getByText('Crear Periodo')).toBeInTheDocument();
    });
    expect(apiClient.callModule.mock.calls.some(([, , metodo]) => metodo === 'PUT')).toBe(false);
    expect(screen.queryByText('2026-IIB')).not.toBeInTheDocument();
  });
});
