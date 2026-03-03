"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { adminAPI, ActividadRow, ResumenActividad, extractError } from "@/lib/api";
import { ArrowLeft, Clock, FileSearch, MessageSquare, Users } from "lucide-react";
import Link from "next/link";

export default function ActividadPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [resumen, setResumen] = useState<ResumenActividad | null>(null);
  const [rows, setRows] = useState<ActividadRow[]>([]);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState("");

  // Filtros
  const [filtroAccion, setFiltroAccion] = useState("");
  const [filtroFechaInicio, setFiltroFechaInicio] = useState("");
  const [filtroFechaFin, setFiltroFechaFin] = useState("");

  useEffect(() => {
    if (!loading && (!user || user.rol !== "admin")) {
      router.push("/login");
    }
  }, [user, loading, router]);

  useEffect(() => {
    if (user?.rol === "admin") {
      cargarResumen();
      cargarActividad();
    }
  }, [user]);

  async function cargarResumen() {
    try {
      const res = await adminAPI.getResumenActividad();
      setResumen(res.data);
    } catch {
      // No crítico
    }
  }

  async function cargarActividad() {
    setFetching(true);
    setError("");
    try {
      const res = await adminAPI.getActividad({
        accion: filtroAccion || undefined,
        fecha_inicio: filtroFechaInicio || undefined,
        fecha_fin: filtroFechaFin || undefined,
      });
      setRows(res.data);
    } catch (err) {
      setError(extractError(err, "Error al cargar la actividad"));
    } finally {
      setFetching(false);
    }
  }

  function formatDuracion(seg: number | null): string {
    if (seg === null || seg === undefined) return "—";
    if (seg < 60) return `${seg}s`;
    const min = Math.floor(seg / 60);
    const s = Math.round(seg % 60);
    return `${min}m ${s}s`;
  }

  function formatFecha(ts: string): string {
    if (!ts) return "—";
    try {
      return new Date(ts).toLocaleString("es-PE", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
    } catch {
      return ts;
    }
  }

  if (loading || !user) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8">

        {/* Encabezado */}
        <div className="flex items-center gap-3 mb-6">
          <Link href="/admin" className="text-gray-500 hover:text-gray-700">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">Reporte de Actividad</h1>
        </div>

        {/* Tarjetas de resumen */}
        {resumen && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-white rounded-xl shadow-sm p-5 border border-gray-100">
              <div className="flex items-center gap-2 text-blue-600 mb-1">
                <FileSearch className="w-4 h-4" />
                <span className="text-xs font-semibold uppercase tracking-wide">Auditorías</span>
              </div>
              <p className="text-3xl font-bold text-gray-800">{resumen.total_auditorias}</p>
            </div>
            <div className="bg-white rounded-xl shadow-sm p-5 border border-gray-100">
              <div className="flex items-center gap-2 text-green-600 mb-1">
                <MessageSquare className="w-4 h-4" />
                <span className="text-xs font-semibold uppercase tracking-wide">Preguntas</span>
              </div>
              <p className="text-3xl font-bold text-gray-800">{resumen.total_preguntas}</p>
            </div>
            <div className="bg-white rounded-xl shadow-sm p-5 border border-gray-100">
              <div className="flex items-center gap-2 text-purple-600 mb-1">
                <Clock className="w-4 h-4" />
                <span className="text-xs font-semibold uppercase tracking-wide">Prom. auditoría</span>
              </div>
              <p className="text-3xl font-bold text-gray-800">
                {formatDuracion(resumen.duracion_promedio_auditoria)}
              </p>
            </div>
            <div className="bg-white rounded-xl shadow-sm p-5 border border-gray-100">
              <div className="flex items-center gap-2 text-orange-600 mb-1">
                <Clock className="w-4 h-4" />
                <span className="text-xs font-semibold uppercase tracking-wide">Prom. pregunta</span>
              </div>
              <p className="text-3xl font-bold text-gray-800">
                {formatDuracion(resumen.duracion_promedio_pregunta)}
              </p>
            </div>
          </div>
        )}

        {/* Top usuarios */}
        {resumen && resumen.top_usuarios.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm p-5 border border-gray-100 mb-8">
            <div className="flex items-center gap-2 mb-3">
              <Users className="w-4 h-4 text-gray-500" />
              <h2 className="font-semibold text-gray-700">Top usuarios más activos</h2>
            </div>
            <div className="flex flex-wrap gap-3">
              {resumen.top_usuarios.map((u) => (
                <div key={u.email} className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-sm">
                  <span className="font-medium text-gray-800">{u.email}</span>
                  <span className="ml-2 text-gray-500">{u.total} ops</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Filtros */}
        <div className="bg-white rounded-xl shadow-sm p-5 border border-gray-100 mb-6">
          <h2 className="font-semibold text-gray-700 mb-4">Filtros</h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Tipo</label>
              <select
                value={filtroAccion}
                onChange={(e) => setFiltroAccion(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Todos</option>
                <option value="auditoria">Auditorías</option>
                <option value="pregunta">Preguntas</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Desde</label>
              <input
                type="date"
                value={filtroFechaInicio}
                onChange={(e) => setFiltroFechaInicio(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Hasta</label>
              <input
                type="date"
                value={filtroFechaFin}
                onChange={(e) => setFiltroFechaFin(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={cargarActividad}
                disabled={fetching}
                className="w-full bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {fetching ? "Cargando..." : "Aplicar filtros"}
              </button>
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 mb-4 text-sm">
            {error}
          </div>
        )}

        {/* Tabla */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100">
            <h2 className="font-semibold text-gray-700">
              Historial de actividad
              {rows.length > 0 && (
                <span className="ml-2 text-sm font-normal text-gray-400">({rows.length} registros)</span>
              )}
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-100">
              <thead className="bg-gray-50">
                <tr>
                  {["Usuario", "Tipo", "Canal", "Duración", "Hallazgos", "Detalle", "Fecha"].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-gray-400 text-sm">
                      {fetching ? "Cargando..." : "No hay registros para los filtros seleccionados."}
                    </td>
                  </tr>
                ) : (
                  rows.map((row) => (
                    <tr key={row.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3">
                        <div className="text-sm font-medium text-gray-800">{row.email || "—"}</div>
                        <div className="text-xs text-gray-400">{row.rol || ""}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          row.accion === "auditoria"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-green-100 text-green-700"
                        }`}>
                          {row.accion === "auditoria" ? "Auditoría" : "Pregunta"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          row.canal === "web"
                            ? "bg-purple-100 text-purple-700"
                            : "bg-gray-100 text-gray-600"
                        }`}>
                          {row.canal || "bot"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {formatDuracion(row.duracion_segundos)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {row.n_hallazgos !== null && row.n_hallazgos !== undefined
                          ? row.n_hallazgos
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm text-gray-600 max-w-xs truncate block" title={row.detalle}>
                          {row.detalle || "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">
                        {formatFecha(row.timestamp)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}
