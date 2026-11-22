import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { StudentReportCard } from '../modules/evaluation/StudentReportCard';

vi.mock('../core/auth/useAuth', () => ({
  useAuth: () => ({
    user: { id: 2315, roles: ['estudiante'], full_name: 'Ana Gómez' },
    openPasswordModal: vi.fn()
  })
}));

const boletinConNotas = {
  estudiante: {
    id: 2315,
    nombres: 'Ana',
    apellidos: 'Gómez',
    codigo_estudiante: '2026-0001',
    dni: '12345678',
    periodo_codigo: '2026-I',
    programa_nombre: 'Desarrollo de Sistemas de Información',
    fecha_emision: '17/11/2026'
  },
  matricula_estado: { pago_matricula: true },
  estado_academico: 'regular',
  progreso_creditos: { creditos_aprobados: 4, creditos_totales: 20, porcentaje: 20 },
  cursos_periodo: [
    { unidad_nombre: 'Taller Web', creditos: 4, nota_final: 16, estado: 'aprobado' }
  ],
  ciclos: [
    {
      ciclo: 1,
      titulo: 'CICLO I',
      promedio: 16,
      creditos_ciclo: 4,
      creditos_aprobados: 4,
      completado: false,
      unidades: [
        { nombre: 'Taller Web', creditos: 4, nota: 16, estado: 'aprobado' }
      ]
    }
  ],
  resumen: {
    promedio_general: 16,
    cursos_aprobados: 1,
    cursos_desaprobados: 0,
    total_cursos: 1,
    ciclos_completados: 0,
    ciclos_totales: 1
  },
  historial: [],
  observaciones: null
};

const boletinSinNotas = {
  ...boletinConNotas,
  cursos_periodo: [],
  ciclos: [
    {
      ciclo: 1,
      titulo: 'CICLO I',
      promedio: null,
      creditos_ciclo: 4,
      creditos_aprobados: 0,
      completado: false,
      unidades: [
        { nombre: 'Taller Web', creditos: 4, nota: null, estado: 'pendiente' }
      ]
    }
  ],
  resumen: {
    promedio_general: null,
    cursos_aprobados: 0,
    cursos_desaprobados: 0,
    total_cursos: 0,
    ciclos_completados: 0,
    ciclos_totales: 1
  }
};

describe('Boletín de notas - StudentReportCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renderiza los datos del backend sin depender de archivos JSON locales', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => boletinConNotas
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<StudentReportCard />);

    expect((await screen.findAllByText(/Gómez, Ana/i)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('CICLO I')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/Taller Web/i)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Sin notas registradas/i)).not.toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/mod-gestion-academica/estudiantes/2315/boletin',
      expect.objectContaining({ headers: expect.any(Object) })
    );
  });

  it('muestra un aviso claro cuando el backend no tiene evaluaciones registradas', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => boletinSinNotas
    }));

    render(<StudentReportCard />);

    expect(await screen.findByText(/Sin notas registradas/i)).toBeInTheDocument();
    expect(screen.getByText(/aún no tiene evaluaciones registradas/i)).toBeInTheDocument();
    expect(screen.queryByText(/No se pudo cargar/i)).not.toBeInTheDocument();
  });

  it('muestra el error del backend sin romper la pantalla', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Error interno del servidor' })
    }));

    render(<StudentReportCard />);

    expect(await screen.findByText('Error interno del servidor')).toBeInTheDocument();
    expect(screen.queryByText(/Sin notas registradas/i)).not.toBeInTheDocument();
  });

  it('muestra correctamente la carrera, ciclo y cursos con nota 15 guardada por el docente', async () => {
    const boletinNota15 = {
      ...boletinConNotas,
      estudiante: {
        ...boletinConNotas.estudiante,
        programa_nombre: 'Mecatrónica Automotriz'
      },
      cursos_periodo: [
        { unidad_nombre: 'Sistemas Electrónicos del Automóvil', creditos: 4, nota_final: 15, estado: 'aprobado' }
      ],
      ciclos: [
        {
          ciclo: 1,
          titulo: 'CICLO I',
          promedio: 15,
          creditos_ciclo: 4,
          creditos_aprobados: 4,
          completado: true,
          unidades: [
            { nombre: 'Sistemas Electrónicos del Automóvil', creditos: 4, nota: 15, estado: 'aprobado' }
          ]
        }
      ],
      resumen: {
        promedio_general: 15,
        cursos_aprobados: 1,
        cursos_desaprobados: 0,
        total_cursos: 1,
        ciclos_completados: 1,
        ciclos_totales: 1
      }
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => boletinNota15
    }));

    render(<StudentReportCard />);

    expect((await screen.findAllByText('Mecatrónica Automotriz')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('CICLO I')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/Sistemas Electrónicos del Automóvil/i)).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('15')).length).toBeGreaterThan(0);
  });
});
