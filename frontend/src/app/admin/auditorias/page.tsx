"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { adminAPI, contractsAPI, AdminAuditRow, extractError } from "@/lib/api";
import {
  ArrowLeft,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertCircle,
  Clock,
  Terminal,
  X,
  Eye,
} from "lucide-react";
import Link from "next/link";

type AuditLog = { ts: string; nivel: string; msg: string };

const MODEL_LABEL: Record<string, string> = {
  "gemini-2.5-pro": "Gemini 2.5",
  "gemini-3.1-pro-preview": "Gemini 3.1",
  "claude-sonnet-4-6": "Claude Sonnet",
  "claude-opus-4-6": "Claude Opus",
};

function StatusBadge({ status, queuePosition }: { status: string; queuePosition?: number | null }) {
  if (status === "done")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full">
        <CheckCircle2 className="w-3 h-3" />Completada
      </span>
    );
  if (status === "error")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">
        <XCircle className="w-3 h-3" />Error
      </span>
    );
  if (status === "queued")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
        <Clock className="w-3 h-3" />En cola{queuePosition != null ? ` · #${queuePosition}` : ""}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">
      <Loader2 className="w-3 h-3 animate-spin" />En proceso
    </span>
  );
}

function formatDate(iso: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-PE", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export default function AdminAuditoriasPage() {
  const { isAdmin, isAuthenticated } = useAuth();
  const router = useRouter();

  const [rows, setRows] = useState<AdminAuditRow[]>([]);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  // Panel de diagnóstico
  const [diagAuditId, setDiagAuditId] = useState<string | null>(null);
  const [diagLogs, setDiagLogs] = useState<AuditLog[]>([]);
  const [diagStatus, setDiagStatus] = useState<string>("");
  const [diagFilename, setDiagFilename] = useState<string>("");
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isAuthenticated) { router.push("/login"); return; }
    if (!isAdmin) { router.push("/dashboard"); return; }
  }, [isAuthenticated, isAdmin, router]);

  const cargar = useCallback(async () => {
    setFetching(true);
    setError("");
    try {
      const res = await adminAPI.getTodasAuditorias();
      setRows(res.data);
      setLastRefresh(new Date());
    } catch (err) {
      setError(extractError(err, "Error al cargar auditorías"));
    } finally {
      setFetching(false);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) cargar();
  }, [isAdmin, cargar]);

  // Auto-refresh cada 10s si hay auditorías en proceso o en cola
  useEffect(() => {
    const hayActivas = rows.some((r) => r.status === "processing" || r.status === "queued");
    if (!hayActivas) return;
    const id = setInterval(cargar, 10_000);
    return () => clearInterval(id);
  }, [rows, cargar]);

  const handleCancel = async (audit_id: string) => {
    if (!confirm("¿Cancelar esta auditoría? No se puede deshacer.")) return;
    setCancelling(audit_id);
    try {
      await adminAPI.cancelAuditAdmin(audit_id);
      setRows((prev) =>
        prev.map((a) =>
          a.audit_id === audit_id
            ? { ...a, status: "error", error_detail: "Cancelada por el administrador.", progress_msg: "Cancelada por admin" }
            : a
        )
      );
    } catch {
      alert("No se pudo cancelar la auditoría.");
    } finally {
      setCancelling(null);
    }
  };

  // Polling del panel de diagnóstico
  useEffect(() => {
    if (!diagAuditId) return;
    const fetchDiag = async () => {
      try {
        const res = await contractsAPI.getAudit(diagAuditId);
        setDiagLogs(res.data.audit_logs || []);
        setDiagStatus(res.data.status);
        if (res.data.filename) setDiagFilename(res.data.filename);
      } catch { /* silencioso */ }
    };
    fetchDiag();
    const active = diagStatus === "processing" || diagStatus === "queued";
    if (!active) return;
    const id = setInterval(fetchDiag, 3_000);
    return () => clearInterval(id);
  }, [diagAuditId, diagStatus]);

  // Auto-scroll al último log
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [diagLogs]);

  const openDiag = (row: AdminAuditRow) => {
    setDiagLogs([]);
    setDiagStatus(row.status);
    setDiagFilename(row.filename || "");
    setDiagAuditId(row.audit_id);
  };

  if (!isAdmin) return null;

  const enProceso = rows.filter((r) => r.status === "processing").length;
  const enCola = rows.filter((r) => r.status === "queued").length;

  return (
    <>
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8">

        {/* Encabezado */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Link href="/admin" className="text-gray-500 hover:text-gray-700">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Auditorías de todos los usuarios</h1>
              {lastRefresh && (
                <p className="text-xs text-gray-400 mt-0.5">
                  Actualizado: {lastRefresh.toLocaleTimeString("es-PE")}
                  {(enProceso > 0 || enCola > 0) && (
                    <span className="ml-2 text-blue-500">
                      · auto-refresh activo ({[enProceso > 0 && `${enProceso} en curso`, enCola > 0 && `${enCola} en cola`].filter(Boolean).join(", ")})
                    </span>
                  )}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={cargar}
            disabled={fetching}
            className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 bg-white border border-slate-200 px-4 py-2 rounded-lg shadow-sm hover:shadow transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${fetching ? "animate-spin" : ""}`} />
            Actualizar
          </button>
        </div>

        {/* Stats rápidas */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-xl shadow-sm p-4 border border-gray-100 text-center">
            <p className="text-2xl font-bold text-gray-800">{rows.length}</p>
            <p className="text-xs text-gray-500 mt-1">Total auditorías</p>
          </div>
          <div className="bg-white rounded-xl shadow-sm p-4 border border-gray-100 text-center">
            <p className="text-2xl font-bold text-blue-600">{enProceso}</p>
            <p className="text-xs text-gray-500 mt-1">En proceso</p>
          </div>
          <div className="bg-white rounded-xl shadow-sm p-4 border border-gray-100 text-center">
            <p className="text-2xl font-bold text-amber-600">{enCola}</p>
            <p className="text-xs text-gray-500 mt-1">En cola</p>
          </div>
          <div className="bg-white rounded-xl shadow-sm p-4 border border-gray-100 text-center">
            <p className="text-2xl font-bold text-green-600">{rows.filter((r) => r.status === "done").length}</p>
            <p className="text-xs text-gray-500 mt-1">Completadas</p>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 mb-4 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Tabla */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-100">
              <thead className="bg-gray-50">
                <tr>
                  {["Usuario", "Documento", "Modo", "Estado / Progreso", "Hallazgos", "Inicio", ""].map((h) => (
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
                      {fetching ? "Cargando..." : "No hay auditorías registradas."}
                    </td>
                  </tr>
                ) : (
                  rows.map((row) => (
                    <tr
                      key={row.audit_id}
                      className={`hover:bg-gray-50 transition-colors ${row.status === "processing" ? "bg-blue-50/30" : row.status === "queued" ? "bg-amber-50/30" : ""}`}
                    >
                      <td className="px-4 py-3">
                        <div className="text-sm font-medium text-gray-800">{row.email || "—"}</div>
                        <div className="text-xs text-gray-400">{row.rol || ""}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm text-gray-700 max-w-[180px] truncate block" title={row.filename || ""}>
                          {row.filename || "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {row.graph_enabled
                            ? <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700">GraphRAG</span>
                            : <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-600">RAG</span>
                          }
                          {row.modelo_usado && (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-700">
                              {MODEL_LABEL[row.modelo_usado] ?? row.modelo_usado}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={row.status} queuePosition={row.queue_position} />
                        {row.status === "processing" && row.progress_msg && (
                          <p className="text-xs text-gray-400 mt-1">{row.progress_msg}</p>
                        )}
                        {row.status === "processing" && row.progress_pct != null && (
                          <div className="w-24 bg-gray-200 rounded-full h-1 mt-1">
                            <div
                              className="bg-blue-500 h-1 rounded-full transition-all"
                              style={{ width: `${row.progress_pct}%` }}
                            />
                          </div>
                        )}
                        {row.status === "queued" && row.progress_msg && (
                          <p className="text-xs text-amber-500 mt-1">{row.progress_msg}</p>
                        )}
                        {row.status === "error" && row.error_detail && (
                          <p className="text-xs text-red-400 mt-1 max-w-[200px] truncate" title={row.error_detail}>
                            {row.error_detail}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {row.status === "done" && row.n_hallazgos != null ? (
                          <span className={`font-semibold ${row.n_hallazgos > 0 ? "text-amber-600" : "text-green-600"}`}>
                            {row.n_hallazgos}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                        {formatDate(row.created_at)}
                      </td>
                      <td className="px-2 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {row.status === "done" && (
                            <Link
                              href={`/audit?audit_id=${row.audit_id}`}
                              title="Ver informe"
                              className="p-1 text-blue-500 hover:text-blue-700 hover:bg-blue-50 rounded transition-colors"
                            >
                              <Eye className="w-4 h-4" />
                            </Link>
                          )}
                          {(row.status === "processing" || row.status === "queued") && (
                            <>
                              <Link
                                href={`/audit?audit_id=${row.audit_id}`}
                                title={row.status === "queued" ? "Ver estado" : "Ver progreso"}
                                className="p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded transition-colors"
                              >
                                <Eye className="w-4 h-4" />
                              </Link>
                              <button
                                onClick={() => handleCancel(row.audit_id)}
                                disabled={cancelling === row.audit_id}
                                title="Cancelar auditoría"
                                className="p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors disabled:opacity-50"
                              >
                                {cancelling === row.audit_id
                                  ? <Loader2 className="w-4 h-4 animate-spin" />
                                  : <XCircle className="w-4 h-4" />}
                              </button>
                            </>
                          )}
                          <button
                            onClick={() => openDiag(row)}
                            title="Ver diagnóstico"
                            className="p-1 text-violet-400 hover:text-violet-600 hover:bg-violet-50 rounded transition-colors"
                          >
                            <Terminal className="w-4 h-4" />
                          </button>
                        </div>
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
    <>
    {/* Panel de diagnóstico tipo terminal */}
    {diagAuditId && (
      <div className="fixed inset-0 z-50 overflow-hidden">
        {/* Overlay */}
        <div className="absolute inset-0 bg-black/50" onClick={() => setDiagAuditId(null)} />
        {/* Panel lateral derecho */}
        <div className="absolute right-0 top-0 h-full w-full max-w-2xl bg-gray-950 shadow-2xl flex flex-col border-l border-gray-800">
          {/* Cabecera */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <Terminal className="w-4 h-4 text-violet-400 shrink-0" />
              <span className="text-sm font-mono text-violet-400 truncate">
                diagnóstico · {diagFilename || diagAuditId.slice(0, 8) + "..."}
              </span>
              {(diagStatus === "processing" || diagStatus === "queued") && (
                <Loader2 className="w-3 h-3 text-blue-400 animate-spin shrink-0" />
              )}
              {diagStatus === "done" && <CheckCircle2 className="w-3 h-3 text-green-400 shrink-0" />}
              {diagStatus === "error" && <XCircle className="w-3 h-3 text-red-400 shrink-0" />}
            </div>
            <button
              onClick={() => setDiagAuditId(null)}
              className="text-gray-500 hover:text-gray-300 shrink-0 ml-2"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          {/* ID de auditoría */}
          <div className="px-4 py-1.5 bg-gray-900/60 border-b border-gray-800 shrink-0">
            <span className="text-[10px] font-mono text-gray-500">audit_id: {diagAuditId}</span>
          </div>
          {/* Logs */}
          <div className="flex-1 overflow-y-auto px-4 py-3 font-mono text-xs leading-relaxed">
            {diagLogs.length === 0 ? (
              <p className="text-gray-600 italic">Sin logs disponibles para esta auditoría.</p>
            ) : (
              diagLogs.map((log, i) => {
                const color =
                  log.nivel === "ERROR" ? "text-red-400" :
                  log.nivel === "WARN"  ? "text-yellow-400" :
                  "text-green-300";
                const badge =
                  log.nivel === "ERROR" ? "text-red-500" :
                  log.nivel === "WARN"  ? "text-yellow-500" :
                  "text-blue-400";
                const ts = new Date(log.ts).toLocaleTimeString("es-PE", { hour12: false });
                return (
                  <div key={i} className={`mb-0.5 flex gap-2 ${color}`}>
                    <span className="text-gray-600 shrink-0">{ts}</span>
                    <span className={`${badge} shrink-0`}>[{log.nivel}]</span>
                    <span className="whitespace-pre-wrap break-all">{log.msg}</span>
                  </div>
                );
              })
            )}
            {(diagStatus === "processing" || diagStatus === "queued") && (
              <span className="text-green-500 animate-pulse">▌</span>
            )}
            <div ref={logsEndRef} />
          </div>
          {/* Footer */}
          <div className="px-4 py-2 border-t border-gray-800 shrink-0 flex items-center justify-between">
            <span className="text-[10px] text-gray-600 font-mono">{diagLogs.length} entradas</span>
            {(diagStatus === "processing" || diagStatus === "queued") && (
              <span className="text-[10px] text-blue-500 font-mono animate-pulse">● actualizando cada 3s</span>
            )}
          </div>
        </div>
      </div>
    )}
    </>
    </>
  );
}
