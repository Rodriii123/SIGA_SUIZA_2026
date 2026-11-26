import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { CoordinatorAcademic } from '../modules/academic/CoordinatorAcademic';
import { apiClient } from '../core/api/client';

vi.mock('../core/auth/useAuth', () => ({
  useAuth: () => ({
    user: { id: 2, email: 'coordinador.dsi@siga.edu', role: 'coordinador_programa' },
    openPasswordModal: vi.fn()
  })
}));

vi.mock('../core/api/client', () => ({
  apiClient: {
    request: vi.fn()
  }
}));

function mockApi(periodos) {
  apiClient.request.mockImplementation((endpoint) => {
    if (endpoint === '/api/mod-programas-estudio/programas') {
      return Promise.resolve([{ id: 1, nombre: 'Desarrollo de Sistemas de Información' }]);
    }
    if (endpoint === '/api/mod-programas-estudio/periodos') {
      return Promise.resolve(periodos);
    }
    if (endpoint === '/api/mod-usuarios/personal') {
      return Promise.resolve([
        {
          usuario: { id: 2, email: 'coordinador.dsi@siga.edu' },
          perfil: {
            cargo_funcional: 'COORDINADOR_PROGRAMA',
            programa_estudio_id: 1
          }
        }
      ]);
    }
    if (endpoint === '/api/mod-usuarios/usuarios') {
      return Promise.resolve([]);
    }
    if (endpoint.endsWith('/malla')) {
      return Promise.resolve([]);
    }
    if (endpoint.includes('/carga-lectiva') || endpoint.includes('/horarios')) {
      return Promise.resolve([]);
    }
    return Promise.resolve([]);
  });
}

describe('Coordinación de Programa - Clonar carga lectiva', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('explica que no hay periodos de origen cuando solo existe el periodo actual', async () => {
    mockApi([
      {
        id: 1,
        codigo: '2026-I',
        estado: 'matricula_abierta',
        fecha_inicio: '2026-05-14T00:00:00'
      }
    ]);

    render(<CoordinatorAcademic />);

    fireEvent.click(await screen.findByText('Clonar periodo anterior'));

    expect(await screen.findByText('No hay períodos de origen disponibles')).toBeInTheDocument();
    expect(screen.getByText(/Un administrador debe crear el periodo académico previo/i)).toBeInTheDocument();
    expect(screen.queryByText('Periodo de Origen')).not.toBeInTheDocument();
    expect(screen.getByText('Clonar Asignaciones').closest('button')).toBeDisabled();
  });

  it('muestra y preselecciona el periodo anterior, sin ofrecer periodos futuros', async () => {
    mockApi([
      { id: 1, codigo: '2025-II', estado: 'historico', fecha_inicio: '2025-08-01T00:00:00' },
      { id: 2, codigo: '2026-I', estado: 'matricula_abierta', fecha_inicio: '2026-05-14T00:00:00' },
      { id: 3, codigo: '2026-II', estado: 'planificacion', fecha_inicio: '2026-08-03T00:00:00' }
    ]);

    render(<CoordinatorAcademic />);

    fireEvent.click(await screen.findByText('Clonar periodo anterior'));

    const selector = await screen.findByDisplayValue('2025-II (historico)');
    expect(selector).toHaveValue('1');
    expect(screen.getByRole('option', { name: '2025-II (historico)' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /2026-II/ })).not.toBeInTheDocument();
    expect(screen.getByText('2026-I (matricula_abierta)')).toBeInTheDocument();
  });

  it('envía el periodo anterior preseleccionado como origen al clonar', async () => {
    mockApi([
      { id: 1, codigo: '2025-II', estado: 'historico', fecha_inicio: '2025-08-01T00:00:00' },
      { id: 2, codigo: '2026-I', estado: 'matricula_abierta', fecha_inicio: '2026-05-14T00:00:00' }
    ]);

    render(<CoordinatorAcademic />);

    fireEvent.click(await screen.findByText('Clonar periodo anterior'));
    await screen.findByDisplayValue('2025-II (historico)');
    fireEvent.click(screen.getByText('Clonar Asignaciones'));

    await waitFor(() => {
      const call = apiClient.request.mock.calls.find(
        ([endpoint, options]) =>
          endpoint === '/api/mod-programas-estudio/programas/1/carga-lectiva/clonar' &&
          options?.method === 'POST'
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body)).toEqual({
        from_periodo_id: 1,
        to_periodo_id: 2
      });
    });
  });
});
