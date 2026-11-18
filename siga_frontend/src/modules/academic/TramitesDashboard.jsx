import { useState, useEffect, useMemo } from 'react';
import { apiClient } from '../../core/api/client';
import { Plus, Eye, FileText, Repeat, GraduationCap } from 'lucide-react';
import { ConvalidacionesTab } from './ConvalidacionesTab';
import { BecasTab } from './BecasTab';

const BASE = '/api/mod-gestion-academica';
const TIPOS_TRAMITE = [
  'Constancia de Estudios',
  'Certificado de Estudios',
  'Reserva de Matrícula',
  'Constancia de Egreso',
  'Duplicado de Carné',
  'Otro',
];
const FORM_VACIO = { estudiante_id: '', tipo_tramite: TIPOS_TRAMITE[0], observaciones: '' };

const extraerLista = (respuesta, etiqueta) => {
  if (Array.isArray(respuesta)) return respuesta;
  if (respuesta && Array.isArray(respuesta.data)) return respuesta.data;
  throw new Error(`Respuesta inválida al cargar ${etiqueta}.`);
};

export function TramitesDashboard() {
  const [activeTab, setActiveTab] = useState('solicitudes');
  const [loading, setLoading] = useState(false);

  // States for Solicitudes (TUPA)
  const [solicitudes, setSolicitudes] = useState([]);
  const [estudiantes, setEstudiantes] = useState([]);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [success, setSuccess] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(FORM_VACIO);

  const nombreEstudiante = useMemo(
    () => new Map(estudiantes.map(e => [e.id, `${e.apellidos}, ${e.nombres}`])),
    [estudiantes]
  );

  const fetchSolicitudes = async () => {
    setLoading(true);
    setError('');
    const estudiantesPromise = apiClient.request(`${BASE}/estudiantes/`).catch(() => []);
    try {
      const respuesta = await apiClient.request(`${BASE}/tramites/`);
      const tramites = extraerLista(respuesta, 'los trámites');
      const estudiantesResp = await estudiantesPromise;
      const listaEstudiantes = Array.isArray(estudiantesResp) ? estudiantesResp : [];
      setEstudiantes(listaEstudiantes);
      const nombres = new Map(listaEstudiantes.map(e => [e.id, `${e.apellidos}, ${e.nombres}`]));
      setSolicitudes(tramites.map(t => ({ ...t, nombre_alumno: nombres.get(t.estudiante_id) })));
    } catch (err) {
      console.error(err);
      const estudiantesResp = await estudiantesPromise;
      setEstudiantes(Array.isArray(estudiantesResp) ? estudiantesResp : []);
      setError('No se pudieron cargar los trámites.');
      setSolicitudes([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'solicitudes') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchSolicitudes();
    }
  }, [activeTab]);

  const abrirFormulario = () => {
    setFormError('');
    setSuccess('');
    setShowForm(v => !v);
  };

  const guardarSolicitud = async (e) => {
    e.preventDefault();
    setFormError('');
    setSuccess('');
    const estudianteId = parseInt(form.estudiante_id, 10);
    if (!Number.isInteger(estudianteId)) {
      setFormError('Seleccione un estudiante.');
      return;
    }
    if (!form.tipo_tramite.trim()) {
      setFormError('Seleccione el tipo de trámite.');
      return;
    }

    setSaving(true);
    try {
      await apiClient.request(`${BASE}/tramites/`, {
        method: 'POST',
        body: JSON.stringify({
          estudiante_id: estudianteId,
          tipo_tramite: form.tipo_tramite.trim(),
          observaciones: form.observaciones.trim() || null,
        }),
      });
      setForm(FORM_VACIO);
      setShowForm(false);
      setSuccess('Solicitud registrada correctamente.');
      await fetchSolicitudes();
    } catch (err) {
      console.error(err);
      setFormError(err?.message || 'No se pudo registrar la solicitud.');
    } finally {
      setSaving(false);
    }
  };

  const handleEstadoChange = async (id, newEstado) => {
    const anterior = solicitudes;
    setSolicitudes(prev => prev.map(s => s.id === id ? { ...s, estado: newEstado } : s));
    try {
      await apiClient.request(`${BASE}/tramites/${id}/estado?estado=${newEstado}`, { method: 'PUT' });
    } catch (err) {
      console.error(err);
      setSolicitudes(anterior);
      setError('No se pudo actualizar el estado del trámite.');
    }
  };

  const renderTabHeader = (id, label, icon) => (
    <button
      onClick={() => setActiveTab(id)}
      className={`px-5 py-3 rounded-t-xl font-bold transition-colors flex items-center space-x-2 ${
        activeTab === id 
          ? 'bg-white text-primary border-t-2 border-primary shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)] z-10 relative' 
          : 'bg-slate-100 text-slate-500 hover:bg-slate-200 border-b border-slate-300'
      }`}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </button>
  );

  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center">
        <div>
          <h3 className="text-3xl font-bold tracking-tight text-slate-text">
            Gestión de <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-500 to-orange-500">Trámites y Casuísticas</span>
          </h3>
          <p className="text-slate-500 text-sm mt-1">Administración TUPA, Convalidaciones, Becas y Resoluciones</p>
        </div>
      </div>

      <div className="w-full">
        <div className="flex border-b-0 space-x-1">
          {renderTabHeader('solicitudes', 'Trámites y Solicitudes', <FileText size={16} />)}
          {renderTabHeader('convalidaciones', 'Convalidaciones', <Repeat size={16} />)}
          {renderTabHeader('becas', 'Becas y Beneficios', <GraduationCap size={16} />)}
        </div>

        <div className="glass-card rounded-tl-none p-6 min-h-[500px]">
          {activeTab === 'solicitudes' && (
            <div className="space-y-6 animate-fade-in">
              <div className="flex justify-between items-center mb-4">
                <h4 className="text-lg font-bold text-slate-700">Solicitudes Ingresadas</h4>
                <button
                  type="button"
                  onClick={abrirFormulario}
                  className="btn-primary py-1.5 px-4 text-sm rounded-lg flex items-center gap-1.5"
                >
                  <Plus size={16} /> {showForm ? 'Cancelar' : 'Nueva Solicitud Manual'}
                </button>
              </div>

              {error && <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>}
              {success && <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">{success}</div>}

              {showForm && (
                <form onSubmit={guardarSolicitud} className="grid md:grid-cols-2 gap-3 p-4 rounded-xl border border-slate-200 bg-slate-50/50">
                  {formError && (
                    <div className="md:col-span-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                      {formError}
                    </div>
                  )}
                  <select
                    aria-label="Estudiante"
                    className="input-field"
                    value={form.estudiante_id}
                    onChange={e => setForm({ ...form, estudiante_id: e.target.value })}
                    required
                  >
                    <option value="">Estudiante...</option>
                    {estudiantes.map(s => (
                      <option key={s.id} value={s.id}>{s.apellidos}, {s.nombres} ({s.dni})</option>
                    ))}
                  </select>
                  <select
                    aria-label="Tipo de trámite"
                    className="input-field"
                    value={form.tipo_tramite}
                    onChange={e => setForm({ ...form, tipo_tramite: e.target.value })}
                    required
                  >
                    {TIPOS_TRAMITE.map(t => <option key={t}>{t}</option>)}
                  </select>
                  <textarea
                    aria-label="Observaciones"
                    className="input-field md:col-span-2"
                    rows={2}
                    placeholder="Observaciones (opcional)"
                    value={form.observaciones}
                    onChange={e => setForm({ ...form, observaciones: e.target.value })}
                  />
                  <div className="md:col-span-2">
                    <button type="submit" disabled={saving} className="btn-primary px-6 py-2 rounded-lg">
                      {saving ? 'Registrando...' : 'Registrar solicitud'}
                    </button>
                  </div>
                </form>
              )}

              {loading ? (
                <div className="text-center py-10"><div className="w-8 h-8 border-4 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto"></div></div>
              ) : error ? null : solicitudes.length === 0 ? (
                <div className="text-center py-12 text-slate-400">
                  <FileText size={32} className="mx-auto mb-2" />
                  No hay solicitudes registradas.
                </div>
              ) : (
                <table className="w-full text-left text-sm border-collapse">
                  <thead className="bg-slate-50/80 border-y border-slate-200">
                    <tr>
                      <th className="py-3 px-4 font-bold text-slate-600">ID / Fecha</th>
                      <th className="py-3 px-4 font-bold text-slate-600">Estudiante</th>
                      <th className="py-3 px-4 font-bold text-slate-600">Tipo de Trámite</th>
                      <th className="py-3 px-4 font-bold text-slate-600">Estado</th>
                      <th className="py-3 px-4 font-bold text-slate-600 text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {solicitudes.map(s => {
                      const estado = s.estado || 'pendiente';
                      return (
                        <tr key={s.id} className="hover:bg-primary/5 transition-colors">
                          <td className="py-3 px-4">
                            <span className="font-semibold text-slate-700">#{s.id}</span>
                            <div className="text-xs text-slate-500">{s.fecha_solicitud || 'Sin fecha'}</div>
                          </td>
                          <td className="py-3 px-4 font-semibold text-slate-700">{s.nombre_alumno || nombreEstudiante.get(s.estudiante_id) || `Estudiante #${s.estudiante_id}`}</td>
                          <td className="py-3 px-4 font-medium text-slate-600">{s.tipo_tramite}</td>
                          <td className="py-3 px-4">
                            <span className={`badge ${
                              estado === 'pendiente' ? 'badge-amber' :
                              estado === 'en_proceso' ? 'badge-blue' :
                              estado === 'emitido' || estado === 'aprobado' ? 'badge-green' :
                              'badge-slate'
                            }`}>
                              {estado.replace('_', ' ')}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <select
                              className="input-field text-xs mr-2 py-1.5"
                              aria-label={`Estado del trámite ${s.id}`}
                              value={estado}
                              onChange={(e) => handleEstadoChange(s.id, e.target.value)}
                            >
                              <option value="pendiente">Pendiente</option>
                              <option value="en_proceso">En Proceso</option>
                              <option value="emitido">Emitido / Aprobado</option>
                              <option value="rechazado">Rechazado</option>
                            </select>
                            <button className="btn-icon text-slate-400 hover:text-amber-600" title="Ver Detalles">
                              <Eye size={18} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {activeTab === 'convalidaciones' && <ConvalidacionesTab />}

          {activeTab === 'becas' && <BecasTab />}
        </div>
      </div>
    </div>
  );
}
