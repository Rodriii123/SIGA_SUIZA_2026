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

  it('muestra un botón Editar por periodo y permite buscar/filtrar', async () => {
    renderManager();

    expect(await screen.findByText('2026-I')).toBeInTheDocument();
    expect(screen.getByTestId('editar-periodo-1')).toBeInTheDocument();
    expect(screen.getByTestId('editar-periodo-2')).toBeInTheDocument();
    expect(screen.getByText(/Vinculado a: 12 matrículas/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Buscar periodos'), { target: { value: 'segundo' } });
    expect(screen.queryByText('2026-I')).not.toBeInTheDocument();
    expect(screen.getByText('2026-II')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Buscar periodos'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Filtrar por estado'), { target: { value: 'en_curso' } });
    expect(screen.getByText('2026-I')).toBeInTheDocument();
    expect(screen.queryByText('2026-II')).not.toBeInTheDocument();
  });

  it('precarga los datos actuales y guarda los cambios con confirmación y recarga', async () => {
    const onUpdate = vi.fn();
    renderManager(onUpdate);

    fireEvent.click(await screen.findByTestId('editar-periodo-1'));

    expect(screen.getByLabelText('Código del Periodo')).toHaveValue('2026-I');
    expect(screen.getByLabelText('Nombre del Periodo')).toHaveValue('Primer Semestre 2026');
    expect(screen.getByLabelText('Fecha Inicio')).toHaveValue('2026-01-05');
    expect(screen.getByLabelText('Cierre Matrícula Regular')).toHaveValue('2026-02-20');
    expect(screen.getByLabelText('Estado')).toHaveValue('en_curso');
    expect(screen.getByText(/El código permanece bloqueado/)).toBeInTheDocument();
    expect(screen.getByLabelText('Código del Periodo')).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Nombre del Periodo'), {
      target: { value: 'Primer Semestre 2026 (Corregido)' }
    });
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
        nombre: 'Primer Semestre 2026 (Corregido)',
        fecha_fin: '2026-06-25',
        estado: 'en_curso'
      });
    });

    expect(await screen.findByTestId('toast-success')).toBeInTheDocument();
    await waitFor(() => expect(onUpdate).toHaveBeenCalled());
    await waitFor(() => {
      expect(apiClient.callModule.mock.calls.filter(([, , metodo]) => !metodo || metodo === 'GET').length)
        .toBeGreaterThan(1);
    });
  });

  it('conserva la información editada tras una recarga simulada', async () => {
    const primera = renderManager();
    fireEvent.click(await screen.findByTestId('editar-periodo-2'));
    fireEvent.change(screen.getByLabelText('Nombre del Periodo'), { target: { value: 'Segundo Semestre (Validado)' } });
    fireEvent.click(screen.getByTestId('periodo-guardar'));
    fireEvent.click((await screen.findByTestId('confirm-modal')).querySelector('[data-testid="confirm-modal-ok"]'));

    await waitFor(() => expect(periodos[1].nombre).toBe('Segundo Semestre (Validado)'));
    primera.unmount();

    renderManager();
    expect(await screen.findByText('Segundo Semestre (Validado)')).toBeInTheDocument();
    expect(screen.getByText('2026-II')).toBeInTheDocument();
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
    fireEvent.change(screen.getByLabelText('Nombre del Periodo'), { target: { value: 'Cambio temporal' } });
    fireEvent.click(screen.getByText('Cancelar'));

    const confirmacion = await screen.findByTestId('confirm-modal');
    fireEvent.click(within(confirmacion).getByTestId('confirm-modal-ok'));

    await waitFor(() => {
      expect(screen.getByLabelText('Nombre del Periodo')).toHaveValue('');
      expect(screen.getByText('Crear Periodo')).toBeInTheDocument();
    });
    expect(apiClient.callModule.mock.calls.some(([, , metodo]) => metodo === 'PUT')).toBe(false);
    expect(screen.queryByText('Cambio temporal')).not.toBeInTheDocument();
  });
});
