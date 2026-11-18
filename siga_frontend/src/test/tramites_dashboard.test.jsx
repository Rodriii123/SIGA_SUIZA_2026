import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { TramitesDashboard } from '../modules/academic/TramitesDashboard';
import { apiClient } from '../core/api/client';

vi.mock('../core/api/client', () => ({
  apiClient: {
    request: vi.fn()
  }
}));

const estudiante = {
  id: 1,
  apellidos: 'Pérez',
  nombres: 'Ana',
  dni: '12345678'
};

const configurarApi = ({ tramites = [], estudiantes = [estudiante] } = {}) => {
  apiClient.request.mockImplementation((endpoint, options = {}) => {
    if (endpoint === '/api/mod-gestion-academica/tramites/' && options.method === 'POST') {
      return Promise.resolve({
        id: 1,
        estudiante_id: 1,
        tipo_tramite: options.body ? JSON.parse(options.body).tipo_tramite : 'Constancia de Estudios',
        estado: 'pendiente',
        fecha_solicitud: '2026-11-18'
      });
    }
    if (endpoint === '/api/mod-gestion-academica/tramites/') {
      return Promise.resolve(tramites);
    }
    if (endpoint === '/api/mod-gestion-academica/estudiantes/') {
      return Promise.resolve(estudiantes);
    }
    return Promise.resolve([]);
  });
};

describe('Trámites y Casuísticas - TramitesDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('distingue una lista vacía de un error de carga', async () => {
    configurarApi({ tramites: [] });
    render(<TramitesDashboard />);

    expect(await screen.findByText('No hay solicitudes registradas.')).toBeInTheDocument();
    expect(screen.queryByText('No se pudieron cargar los trámites.')).not.toBeInTheDocument();
  });

  it('muestra el error y no la lista vacía cuando falla la consulta', async () => {
    apiClient.request.mockImplementation((endpoint) => {
      if (endpoint === '/api/mod-gestion-academica/tramites/') {
        return Promise.reject(new Error('HTTP error! status: 500'));
      }
      return Promise.resolve([]);
    });

    render(<TramitesDashboard />);

    expect(await screen.findByText('No se pudieron cargar los trámites.')).toBeInTheDocument();
    expect(screen.queryByText('No hay solicitudes registradas.')).not.toBeInTheDocument();
  });

  it('abre el formulario al pulsar Nueva Solicitud Manual', async () => {
    configurarApi({ tramites: [] });
    render(<TramitesDashboard />);

    await screen.findByText('No hay solicitudes registradas.');
    fireEvent.click(screen.getByText('Nueva Solicitud Manual'));

    expect(await screen.findByLabelText('Estudiante')).toBeInTheDocument();
    expect(screen.getByLabelText('Tipo de trámite')).toBeInTheDocument();
    expect(screen.getByLabelText('Observaciones')).toBeInTheDocument();
    expect(screen.getByText('Registrar solicitud')).toBeInTheDocument();
  });

  it('registra la solicitud manual con el payload esperado y recarga la lista', async () => {
    configurarApi({ tramites: [] });
    render(<TramitesDashboard />);

    await screen.findByText('No hay solicitudes registradas.');
    fireEvent.click(screen.getByText('Nueva Solicitud Manual'));

    fireEvent.change(await screen.findByLabelText('Estudiante'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Tipo de trámite'), { target: { value: 'Reserva de Matrícula' } });
    fireEvent.change(screen.getByLabelText('Observaciones'), { target: { value: '  Solicitud de prueba  ' } });
    fireEvent.click(screen.getByText('Registrar solicitud'));

    await waitFor(() => {
      const llamada = apiClient.request.mock.calls.find(
        ([endpoint, options]) => endpoint === '/api/mod-gestion-academica/tramites/' && options?.method === 'POST'
      );
      expect(llamada).toBeTruthy();
    });

    const llamada = apiClient.request.mock.calls.find(
      ([endpoint, options]) => endpoint === '/api/mod-gestion-academica/tramites/' && options?.method === 'POST'
    );
    expect(JSON.parse(llamada[1].body)).toEqual({
      estudiante_id: 1,
      tipo_tramite: 'Reserva de Matrícula',
      observaciones: 'Solicitud de prueba'
    });
    expect(await screen.findByText('Solicitud registrada correctamente.')).toBeInTheDocument();
  });

  it('tolera registros históricos con estado y fecha nulos', async () => {
    configurarApi({
      tramites: [{
        id: 7,
        estudiante_id: 1,
        tipo_tramite: 'Constancia de Estudios',
        estado: null,
        fecha_solicitud: null
      }]
    });

    render(<TramitesDashboard />);

    expect(await screen.findByText('pendiente')).toBeInTheDocument();
    expect(screen.getByText('Sin fecha')).toBeInTheDocument();
    expect(screen.getByText('Pérez, Ana')).toBeInTheDocument();
  });
});
