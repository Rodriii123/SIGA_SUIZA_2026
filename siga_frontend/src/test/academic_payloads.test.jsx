import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { AcademicDashboard } from '../modules/academic/AcademicDashboard';
import { CurriculumMesh } from '../modules/academic/CurriculumMesh';
import { apiClient } from '../core/api/client';

vi.mock('../core/ui/ToastContext', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    confirm: vi.fn().mockResolvedValue(true)
  })
}));

vi.mock('../core/api/client', () => ({
  apiClient: {
    request: vi.fn(),
    callModule: vi.fn()
  }
}));

const programa = {
  id: 1,
  nombre: 'Desarrollo de Sistemas de Información',
  codigo: 'DSI',
  descripcion: 'Carrera de sistemas',
  creditos_totales: 120,
  duracion_periodos: 6,
  modalidad: 'presencial',
  estado: 'activo'
};

describe('Envío de payloads académicos (body, no data)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.scrollTo = vi.fn();

    apiClient.callModule.mockImplementation((module, path) => {
      if (path === 'programas') return Promise.resolve([programa]);
      if (path === 'periodos') return Promise.resolve([{ id: 1, codigo: '2026-I', estado: 'ACTIVO' }]);
      return Promise.resolve([]);
    });

    apiClient.request.mockImplementation((endpoint) => {
      if (endpoint.includes('/configuracion')) {
        return Promise.resolve({ periodo_academico: 1, turnos: ['mañana'], max_estudiantes: 35 });
      }
      return Promise.resolve({});
    });
  });

  it('AcademicDashboard envía el body JSON al editar un programa', async () => {
    render(<AcademicDashboard />);

    fireEvent.click(await screen.findByTitle('Editar información de la carrera'));
    fireEvent.click(await screen.findByText('Guardar Cambios'));

    await waitFor(() => {
      const call = apiClient.request.mock.calls.find(
        ([endpoint, options]) => endpoint === '/api/mod-programas-estudio/programas/1' && options?.method === 'PUT'
      );
      expect(call).toBeTruthy();
    });

    const llamada = apiClient.request.mock.calls.find(
      ([endpoint, options]) => endpoint === '/api/mod-programas-estudio/programas/1' && options?.method === 'PUT'
    );
    expect(llamada[1].body).toEqual(expect.stringContaining('"nombre"'));
    expect(llamada[1].body).toEqual(expect.stringContaining('"codigo"'));
    expect(llamada[1].data).toBeUndefined();
  });

  it('AcademicDashboard envía el body JSON al guardar la parametrización', async () => {
    render(<AcademicDashboard />);

    fireEvent.click(await screen.findByTitle('Configurar turnos, cupos y coordinación'));
    fireEvent.click(await screen.findByText(/Aplicar Parametrizaci/i));

    await waitFor(() => {
      const call = apiClient.request.mock.calls.find(
        ([endpoint, options]) => endpoint === '/api/mod-programas-estudio/programas/1/configuracion' && options?.method === 'POST'
      );
      expect(call).toBeTruthy();
    });

    const llamada = apiClient.request.mock.calls.find(
      ([endpoint, options]) => endpoint === '/api/mod-programas-estudio/programas/1/configuracion' && options?.method === 'POST'
    );
    expect(llamada[1].body).toEqual(expect.stringContaining('"periodo_academico"'));
    expect(llamada[1].body).toEqual(expect.stringContaining('"max_estudiantes"'));
    expect(llamada[1].data).toBeUndefined();
  });

  it('CurriculumMesh envía el body JSON al crear una unidad didáctica', async () => {
    apiClient.request.mockImplementation((endpoint) => {
      if (endpoint.endsWith('/malla')) {
        return Promise.resolve([
          { id: 10, nombre: 'Módulo I', periodo: 1, unidades: [] }
        ]);
      }
      if (endpoint.endsWith('/programas/1')) {
        return Promise.resolve(programa);
      }
      return Promise.resolve({});
    });

    render(<CurriculumMesh programId={1} onBack={vi.fn()} />);

    fireEvent.click(await screen.findByText(/Agregar Unidad Didáctica/i));
    fireEvent.change(screen.getByPlaceholderText(/Taller de Programación Web/i), {
      target: { value: 'Taller Web' }
    });
    fireEvent.click(screen.getByText('Guardar Unidad'));

    await waitFor(() => {
      const call = apiClient.request.mock.calls.find(
        ([endpoint, options]) => endpoint === '/api/mod-programas-estudio/modulos/10/unidades' && options?.method === 'POST'
      );
      expect(call).toBeTruthy();
    });

    const llamada = apiClient.request.mock.calls.find(
      ([endpoint, options]) => endpoint === '/api/mod-programas-estudio/modulos/10/unidades' && options?.method === 'POST'
    );
    expect(llamada[1].body).toEqual(expect.stringContaining('"nombre":"Taller Web"'));
    expect(llamada[1].body).toEqual(expect.stringContaining('"creditos"'));
    expect(llamada[1].data).toBeUndefined();
  });
});
