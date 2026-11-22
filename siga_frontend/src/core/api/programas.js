import { useEffect, useState } from 'react';
import { API_BASE } from './client';

let cache = null;
let inflight = null;

export async function fetchProgramas({ force = false } = {}) {
  if (!force && cache) return cache;
  if (!force && inflight) return inflight;

  const token = localStorage.getItem('token');
  inflight = fetch(`${API_BASE}/api/mod-programas-estudio/programas`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
    .then(async (res) => {
      if (!res.ok) {
        throw new Error(`No se pudo cargar el catálogo de programas (HTTP ${res.status}).`);
      }
      const data = await res.json();
      if (!Array.isArray(data)) {
        throw new Error('El catálogo de programas devolvió una respuesta inválida.');
      }
      cache = data;
      return cache;
    })
    .finally(() => {
      inflight = null;
    });

  return inflight;
}

export function invalidateProgramasCache() {
  cache = null;
}

export function useProgramas() {
  const [programas, setProgramas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let activo = true;
    fetchProgramas()
      .then((lista) => {
        if (activo) {
          setProgramas(lista);
          setError('');
        }
      })
      .catch((err) => {
        if (activo) setError(err.message || 'No se pudo cargar el catálogo de programas.');
      })
      .finally(() => {
        if (activo) setLoading(false);
      });
    return () => {
      activo = false;
    };
  }, []);

  return { programas, loading, error };
}

export function programaNombre(programaId, programas = [], fallback = 'Programa no registrado') {
  if (programaId === null || programaId === undefined || programaId === '') {
    return 'Sin carrera asignada';
  }
  const encontrado = (programas || []).find((p) => String(p.id) === String(programaId));
  return encontrado?.nombre || fallback;
}

export function nombreProgramaEstudiante(student, programas = [], fallback = 'Programa no registrado') {
  return student?.programa_nombre || programaNombre(student?.programa_id, programas, fallback);
}

export function opcionesPrograma(programas = []) {
  return [...programas]
    .filter((p) => p && p.id !== null && p.id !== undefined)
    .sort((a, b) => String(a.nombre || '').localeCompare(String(b.nombre || ''), 'es', { sensitivity: 'base' }))
    .map((p) => ({ value: String(p.id), label: p.nombre || `Programa ${p.id}` }));
}

export function opcionesProgramaConEstudiantes(programas = [], estudiantes = []) {
  const mapa = new Map();
  (programas || []).forEach((p) => {
    if (p && p.id !== null && p.id !== undefined) mapa.set(String(p.id), p.nombre || `Programa ${p.id}`);
  });
  (estudiantes || []).forEach((s) => {
    if (s?.programa_id === null || s?.programa_id === undefined) return;
    const id = String(s.programa_id);
    if (!mapa.has(id)) {
      mapa.set(id, s.programa_nombre || `Programa no registrado (ID ${id})`);
    }
  });
  return [...mapa.entries()]
    .sort((a, b) => a[1].localeCompare(b[1], 'es', { sensitivity: 'base' }))
    .map(([value, label]) => ({ value, label }));
}
