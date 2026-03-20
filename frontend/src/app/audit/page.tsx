"use client";
import { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { contractsAPI, extractError, AuditRow } from "@/lib/api";
import Navbar from "@/components/Navbar";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Upload,
  FileText,
  Loader2,
  Send,
  CheckCircle2,
  AlertCircle,
  MessageSquare,
  FileSearch,
  X,
  Download,
  History,
  Clock,
  Terminal,
} from "lucide-react";

type LogEntry = { ts: string; nivel: string; msg: string };

type Mode = "audit" | "query";
type AuditStatus = "idle" | "uploading" | "ready" | "running" | "done" | "error";

function AuditContent() {
  const { isAuthenticated, user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const mode: Mode = searchParams.get("mode") === "query" ? "query" : "audit";
  const auditIdParam = searchParams.get("audit_id");

  const [status, setStatus] = useState<AuditStatus>("idle");
  const [sessionId, setSessionId] = useState("");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [filename, setFilename] = useState("");
  const [auditResult, setAuditResult] = useState("");
  const [error, setError] = useState("");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "ai"; text: string }[]>([]);
  const [queryLoading, setQueryLoading] = useState(false);
  const [progressMsg, setProgressMsg] = useState("");
  const [isQueued, setIsQueued] = useState(false);
  const [queuePosition, setQueuePosition] = useState<number | null>(null);
  const [graphEnabled] = useState(true);     // Siempre GraphRAG
  const [queryGraphEnabled] = useState(true); // Siempre GraphRAG
  const [modeloSeleccionado, setModeloSeleccionado] = useState("gemini-2.5-pro");
  const [progressPct, setProgressPct] = useState(0);
  const [currentAuditId, setCurrentAuditId] = useState(auditIdParam || "");
  const [pdfLoading, setPdfLoading] = useState(false);
  const [auditHistory, setAuditHistory] = useState<AuditRow[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [activeTab, setActiveTab] = useState<"informe" | "diagnostico">("informe");
  const [diagLogs, setDiagLogs] = useState<LogEntry[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logsPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logsPanelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isAuthenticated) router.push("/login");
  }, [isAuthenticated, router]);

  // Cargar historial de auditorías completadas para el picker de consulta
  useEffect(() => {
    if (mode !== "query") return;
    if (user?.rol !== "auditor" && user?.rol !== "admin") return;
    setLoadingHistory(true);
    contractsAPI.getAudits()
      .then((res) => setAuditHistory(res.data.filter((a) => a.status === "done")))
      .catch(() => {})
      .finally(() => setLoadingHistory(false));
  }, [mode, user]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-scroll del panel de logs de diagnóstico
  useEffect(() => {
    if (logsPanelRef.current) {
      logsPanelRef.current.scrollTop = logsPanelRef.current.scrollHeight;
    }
  }, [diagLogs]);

  // Polling de logs: actualiza cada 5s mientras la auditoría está en curso
  useEffect(() => {
    if (!currentAuditId || status !== "running") return;
    const poll = setInterval(() => {
      contractsAPI.getAuditLogs(currentAuditId)
        .then((res) => setDiagLogs(res.data.logs ?? []))
        .catch(() => {});
    }, 5000);
    logsPollRef.current = poll;
    return () => clearInterval(poll);
  }, [currentAuditId, status]);

  // Logs históricos: cargar cuando la auditoría ya está completada
  useEffect(() => {
    if (status !== "done" || !currentAuditId || diagLogs.length > 0) return;
    contractsAPI.getAuditLogs(currentAuditId)
      .then((res) => setDiagLogs(res.data.logs ?? []))
      .catch(() => {});
  }, [status, currentAuditId]);

  // Si llega con ?audit_id=xxx (desde historial), carga el resultado directamente
  useEffect(() => {
    if (!auditIdParam) return;
    setStatus("running");
    setProgressMsg("Cargando informe...");

    const poll = setInterval(async () => {
      try {
        const check = await contractsAPI.getAudit(auditIdParam);
        if (check.data.progress_msg) setProgressMsg(check.data.progress_msg);
        if (check.data.progress_pct != null) setProgressPct(check.data.progress_pct);
        if (check.data.filename) setFilename(check.data.filename);
        if (check.data.modelo_usado) setModeloSeleccionado(check.data.modelo_usado);
        if (check.data.status === "queued") {
          setIsQueued(true);
          setQueuePosition(check.data.queue_position ?? null);
        } else {
          setIsQueued(false);
        }
        if (check.data.status === "done") {
          clearInterval(poll);
          setProgressPct(100);
          setAuditResult(check.data.informe || "");
          setStatus("done");
        } else if (check.data.status === "error") {
          clearInterval(poll);
          setError(check.data.error_detail || "La auditoría falló.");
          setStatus("error");
        }
      } catch {
        clearInterval(poll);
        setError("Error al cargar la auditoría.");
        setStatus("error");
      }
    }, 3000);
    pollRef.current = poll;
    return () => clearInterval(poll);
  }, [auditIdParam]);

  const handleFileUpload = async (file: File) => {
    if (!file) return;
    setError("");
    setAuditResult("");
    setMessages([]);

    // Modo auditoría: guardar el archivo localmente, sin llamar al API todavía.
    // El archivo se envía al backend solo al pulsar "Iniciar auditoría".
    if (mode === "audit") {
      setUploadedFile(file);
      setFilename(file.name);
      setStatus("ready");
      return;
    }

    // Modo consulta: indexar el contrato para RAG (necesita session_id).
    setStatus("uploading");
    try {
      const res = await contractsAPI.upload(file, queryGraphEnabled);
      setSessionId(res.data.session_id);
      setUploadedFile(file);
      setFilename(res.data.filename);
      setStatus("ready");
    } catch (err: unknown) {
      setError(extractError(err, "Error al subir el contrato. Verifica el archivo e inténtalo de nuevo."));
      setStatus("error");
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFileUpload(file);
  };

  const startAudit = async () => {
    if (!uploadedFile) return;
    setStatus("running");
    setError("");
    setProgressMsg("Iniciando...");
    setProgressPct(5);
    try {
      const res = await contractsAPI.audit(uploadedFile, graphEnabled, modeloSeleccionado);
      const auditId = res.data.audit_id;
      setCurrentAuditId(auditId);
      const poll = setInterval(async () => {
        try {
          const check = await contractsAPI.getAudit(auditId);
          if (check.data.progress_msg) setProgressMsg(check.data.progress_msg);
          if (check.data.progress_pct != null) setProgressPct(check.data.progress_pct);
          if (check.data.modelo_usado) setModeloSeleccionado(check.data.modelo_usado);
          if (check.data.status === "queued") {
            setIsQueued(true);
            setQueuePosition(check.data.queue_position ?? null);
          } else {
            setIsQueued(false);
          }
          if (check.data.status === "done") {
            clearInterval(poll);
            setProgressPct(100);
            setAuditResult(check.data.informe || "");
            setStatus("done");
          } else if (check.data.status === "error") {
            clearInterval(poll);
            setError(check.data.error_detail || "La auditoría falló. Intenta nuevamente.");
            setStatus("ready");
          }
        } catch {
          clearInterval(poll);
          setError("Error al consultar el estado de la auditoría.");
          setStatus("ready");
        }
      }, 4000);
      pollRef.current = poll;
    } catch (err: unknown) {
      const msg = extractError(err, "Error al iniciar la auditoría.");
      if (msg.toLowerCase().includes("en curso") || msg.toLowerCase().includes("proceso")) {
        setError("Ya hay una auditoría en progreso. Por favor espera.");
      } else {
        setError(msg);
      }
      setStatus("ready");
    }
  };

  const loadFromAudit = async (audit: AuditRow) => {
    setStatus("uploading");
    setError("");
    try {
      const res = await contractsAPI.loadAuditAsSession(audit.audit_id);
      setSessionId(res.data.session_id);
      setFilename(res.data.filename);
      setStatus("ready");
    } catch (err: unknown) {
      setError(extractError(err, "No se pudo cargar la auditoría. Sube el contrato manualmente."));
      setStatus("idle");
    }
  };

  const sendQuestion = async () => {
    if (!question.trim() || !sessionId || queryLoading) return;
    const q = question.trim();
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setQuestion("");
    setQueryLoading(true);
    try {
      const res = await contractsAPI.query({ session_id: sessionId, pregunta: q, modelo: modeloSeleccionado });
      setMessages((prev) => [...prev, { role: "ai", text: res.data.respuesta }]);
    } catch {
      setMessages((prev) => [...prev, { role: "ai", text: "❌ Error al procesar la pregunta." }]);
    } finally {
      setQueryLoading(false);
    }
  };

  const downloadPdf = async () => {
    if (!currentAuditId || pdfLoading) return;
    setPdfLoading(true);
    try {
      const res = await contractsAPI.downloadAuditPdf(currentAuditId);
      const blob = new Blob([res.data as BlobPart], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename.replace(/\.\w+$/, "") + "_informe.pdf";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      let msg = "No se pudo generar el PDF.";
      // Intentar leer el mensaje de error del blob (axios con responseType: "blob")
      const errData = (err as { response?: { data?: unknown; status?: number } })?.response?.data;
      if (errData instanceof Blob) {
        try {
          const text = await errData.text();
          const parsed = JSON.parse(text);
          if (parsed?.detail) msg = `Error: ${parsed.detail}`;
        } catch { /* ignorar si no se puede parsear */ }
      }
      alert(msg);
    } finally {
      setPdfLoading(false);
    }
  };

  const reset = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (logsPollRef.current) clearInterval(logsPollRef.current);
    setStatus("idle");
    setSessionId("");
    setUploadedFile(null);
    setFilename("");
    setAuditResult("");
    setMessages([]);
    setError("");
    setProgressMsg("");
    setProgressPct(0);
    setCurrentAuditId("");
    setDiagLogs([]);
    setActiveTab("informe");
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="max-w-4xl mx-auto px-4 py-10">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          {mode === "audit" ? (
            <FileSearch className="w-7 h-7 text-blue-600" />
          ) : (
            <MessageSquare className="w-7 h-7 text-blue-600" />
          )}
          <div>
            <h1 className="text-2xl font-bold text-[#1e3a5f]">
              {mode === "audit" ? "Auditoría de contrato" : "Consulta interactiva"}
            </h1>
            <p className="text-slate-500 text-sm mt-0.5">
              {mode === "audit"
                ? "Análisis completo por agentes IA especializados"
                : "Haz preguntas sobre tu contrato"}
            </p>
          </div>
        </div>

        {/* Picker: auditorías anteriores (solo auditor/admin en modo consulta) */}
        {mode === "query" && (status === "idle" || status === "error") &&
          (user?.rol === "auditor" || user?.rol === "admin") && (
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <History className="w-4 h-4 text-slate-500" />
              <h3 className="font-semibold text-slate-700 text-sm">Consultar una auditoría anterior</h3>
            </div>
            {loadingHistory ? (
              <div className="flex items-center gap-2 text-slate-400 text-sm py-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Cargando historial...</span>
              </div>
            ) : auditHistory.length === 0 ? (
              <p className="text-slate-400 text-sm py-2">No tienes auditorías completadas aún.</p>
            ) : (
              <div className="space-y-2">
                {auditHistory.slice(0, 8).map((a) => (
                  <div
                    key={a.audit_id}
                    className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-100"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <FileText className="w-4 h-4 text-slate-400 flex-shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-[#1e3a5f] truncate max-w-[220px]">
                          {a.filename || "contrato"}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${
                            a.graph_enabled ? "bg-purple-100 text-purple-700" : "bg-blue-50 text-blue-600"
                          }`}>
                            {a.graph_enabled ? "GraphRAG" : "RAG"}
                          </span>
                          <span className="text-xs text-slate-400">
                            {new Date(a.created_at).toLocaleDateString("es-PE")}
                          </span>
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => loadFromAudit(a)}
                      className="text-xs font-medium text-blue-600 hover:text-blue-800 hover:underline whitespace-nowrap ml-3"
                    >
                      Usar esta →
                    </button>
                  </div>
                ))}
              </div>
            )}
            <p className="text-xs text-slate-400 text-center mt-4 pt-3 border-t border-slate-100">
              — o sube un nuevo contrato abajo —
            </p>
          </div>
        )}

        {/* GraphRAG siempre activo — selector eliminado en v9.11 */}

        {/* Selector de modelo LLM (visible en idle/error, ambos modos) */}
        {(status === "idle" || status === "error") && (
          <div className="mb-6">
            <p className="text-sm font-medium text-slate-600 mb-3">Modelo de IA</p>
            <div className={`grid gap-3 ${user?.rol === "admin" ? "sm:grid-cols-2 lg:grid-cols-4" : "sm:grid-cols-2"}`}>
              <button
                onClick={() => setModeloSeleccionado("gemini-2.5-pro")}
                className={`p-4 rounded-xl border-2 text-left transition-all ${
                  modeloSeleccionado === "gemini-2.5-pro"
                    ? "border-blue-500 bg-blue-50"
                    : "border-slate-200 hover:border-slate-300 bg-white"
                }`}
              >
                <div className="font-semibold text-[#1e3a5f] text-sm mb-1">
                  Gemini 2.5 Pro
                  {modeloSeleccionado === "gemini-2.5-pro" && (
                    <span className="ml-2 text-xs text-blue-600 font-medium">✓ Seleccionado</span>
                  )}
                </div>
                <div className="text-xs text-slate-500">Modelo estable. Ideal para la mayoría de contratos.</div>
              </button>
              <button
                onClick={() => setModeloSeleccionado("gemini-3.1-pro-preview")}
                className={`p-4 rounded-xl border-2 text-left transition-all ${
                  modeloSeleccionado === "gemini-3.1-pro-preview"
                    ? "border-emerald-500 bg-emerald-50"
                    : "border-slate-200 hover:border-slate-300 bg-white"
                }`}
              >
                <div className="font-semibold text-[#1e3a5f] text-sm mb-1">
                  Gemini 3.1 Pro Preview
                  {modeloSeleccionado === "gemini-3.1-pro-preview" && (
                    <span className="ml-2 text-xs text-emerald-600 font-medium">✓ Seleccionado</span>
                  )}
                </div>
                <div className="text-xs text-slate-500">Modelo avanzado. Mayor razonamiento y precisión.</div>
              </button>
              {user?.rol === "admin" && (
                <>
                  <button
                    onClick={() => setModeloSeleccionado("claude-sonnet-4-6")}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${
                      modeloSeleccionado === "claude-sonnet-4-6"
                        ? "border-violet-500 bg-violet-50"
                        : "border-slate-200 hover:border-slate-300 bg-white"
                    }`}
                  >
                    <div className="font-semibold text-[#1e3a5f] text-sm mb-1">
                      Claude Sonnet 4.6
                      <span className="ml-1 text-xs text-violet-600 font-medium">Admin</span>
                      {modeloSeleccionado === "claude-sonnet-4-6" && (
                        <span className="ml-2 text-xs text-violet-600 font-medium">✓ Seleccionado</span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500">Anthropic. Balance velocidad/calidad.</div>
                  </button>
                  <button
                    onClick={() => setModeloSeleccionado("claude-opus-4-6")}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${
                      modeloSeleccionado === "claude-opus-4-6"
                        ? "border-orange-500 bg-orange-50"
                        : "border-slate-200 hover:border-slate-300 bg-white"
                    }`}
                  >
                    <div className="font-semibold text-[#1e3a5f] text-sm mb-1">
                      Claude Opus 4.6
                      <span className="ml-1 text-xs text-orange-600 font-medium">Admin</span>
                      {modeloSeleccionado === "claude-opus-4-6" && (
                        <span className="ml-2 text-xs text-orange-600 font-medium">✓ Seleccionado</span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500">Anthropic. Máxima capacidad de razonamiento.</div>
                  </button>
                </>
              )}
            </div>
          </div>
        )}

        {/* Upload area */}
        {status === "idle" || status === "error" ? (
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            className="border-2 border-dashed border-slate-200 hover:border-blue-400 rounded-2xl p-12 text-center transition-colors bg-white cursor-pointer group"
            onClick={() => document.getElementById("file-input")?.click()}
          >
            <input
              id="file-input"
              type="file"
              accept=".pdf,.docx,.doc"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
            />
            <Upload className="w-12 h-12 text-slate-300 group-hover:text-blue-400 mx-auto mb-4 transition-colors" />
            <h3 className="font-semibold text-slate-600 mb-2">
              Arrastra tu contrato aquí o haz clic para seleccionar
            </h3>
            <p className="text-sm text-slate-400">PDF o Word — máximo 10 MB</p>
            {error && (
              <div className="mt-4 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm flex items-center gap-2">
                <AlertCircle className="w-4 h-4" />
                {error}
              </div>
            )}
          </div>
        ) : status === "uploading" ? (
          <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-12 text-center">
            <Loader2 className={`w-10 h-10 animate-spin mx-auto mb-4 ${queryGraphEnabled ? "text-purple-500" : "text-blue-500"}`} />
            <p className="text-slate-600 font-medium">
              {queryGraphEnabled
                ? "Construyendo base de conocimiento RAG + grafo de conocimiento..."
                : "Procesando y vectorizando el contrato..."}
            </p>
            <p className="text-slate-400 text-sm mt-1">
              {queryGraphEnabled
                ? "Esto puede tardar varios minutos. No cierres la página."
                : "Esto puede tomar unos segundos"}
            </p>
          </div>
        ) : (
          <>
            {/* File chip — mostrar cuando hay filename y no está running */}
            {filename && status !== "running" && (
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 mb-6 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-green-50 rounded-xl flex items-center justify-center">
                    <FileText className="w-5 h-5 text-green-600" />
                  </div>
                  <div>
                    <p className="font-medium text-[#1e3a5f] text-sm">{filename}</p>
                    <p className="text-xs text-green-600 flex items-center gap-1 mt-0.5">
                      <CheckCircle2 className="w-3 h-3" />
                      {mode === "audit"
                        ? "Listo para auditar"
                        : queryGraphEnabled
                          ? "Indexado con RAG + GraphRAG"
                          : "Contrato indexado correctamente"}
                    </p>
                  </div>
                </div>
                <button onClick={reset} className="p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-50">
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Audit mode */}
            {mode === "audit" && (
              <div>
                {status === "ready" && (
                  <div>
                    {error && (
                      <div className="bg-amber-50 border border-amber-200 text-amber-700 rounded-xl px-4 py-3 text-sm mb-4 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 flex-shrink-0" />
                        {error}
                      </div>
                    )}

                    {/* GraphRAG siempre activo — selector eliminado en v9.11 */}

                    <div className="text-center">
                    <button
                      onClick={startAudit}
                      disabled={!uploadedFile}
                      className="font-semibold px-8 py-4 rounded-xl transition-colors inline-flex items-center gap-2 text-lg shadow-lg disabled:opacity-50 text-white bg-purple-700 hover:bg-purple-800"
                    >
                      <FileSearch className="w-5 h-5" />
                      Iniciar auditoría profunda
                    </button>
                    <p className="text-slate-400 text-sm mt-3">
                      Los 3 agentes IA analizarán tu contrato (≈ 1 hora)
                    </p>
                    <p className="text-slate-400 text-xs mt-1">
                      Puedes cerrar esta página — recibirás un email cuando termine
                    </p>
                    </div>
                  </div>
                )}

                {status === "running" && (
                  <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-10">
                    {isQueued ? (
                      /* Panel de cola */
                      <div className="text-center">
                        <div className="w-16 h-16 bg-amber-50 rounded-2xl flex items-center justify-center mx-auto mb-4">
                          <Clock className="w-8 h-8 text-amber-500" />
                        </div>
                        <h3 className="font-semibold text-[#1e3a5f] text-lg mb-1">Auditoría en cola</h3>
                        {queuePosition != null && (
                          <p className="text-amber-600 font-bold text-2xl mb-2">#{queuePosition}</p>
                        )}
                        <p className="text-slate-500 text-sm mb-4">
                          Tu auditoría comenzará automáticamente cuando terminen las anteriores.
                        </p>
                        <p className="text-slate-400 text-xs">Puedes cerrar esta página — recibirás un email cuando termine</p>
                      </div>
                    ) : (
                      /* Panel de progreso normal */
                      <>
                        <div className="flex items-center justify-between mb-3">
                          <h3 className="font-semibold text-[#1e3a5f] text-lg">Auditoría en progreso</h3>
                          <span className="text-2xl font-bold text-blue-600 tabular-nums">{progressPct}%</span>
                        </div>

                        <div className="w-full bg-slate-100 rounded-full h-3 overflow-hidden mb-3">
                          <div
                            className="h-3 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 transition-all duration-700 ease-out"
                            style={{ width: `${progressPct}%` }}
                          />
                        </div>

                        {progressMsg && (
                          <p className="text-blue-600 font-medium text-sm mb-3">{progressMsg}</p>
                        )}

                        <div className="flex justify-center mb-4">
                          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${
                            modeloSeleccionado === "gemini-3.1-pro-preview" ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                            : modeloSeleccionado === "claude-sonnet-4-6" ? "bg-violet-50 text-violet-700 border border-violet-200"
                            : modeloSeleccionado === "claude-opus-4-6" ? "bg-orange-50 text-orange-700 border border-orange-200"
                            : "bg-blue-50 text-blue-700 border border-blue-200"
                          }`}>
                            🤖 {
                              modeloSeleccionado === "gemini-3.1-pro-preview" ? "Gemini 3.1 Pro Preview"
                              : modeloSeleccionado === "claude-sonnet-4-6" ? "Claude Sonnet 4.6"
                              : modeloSeleccionado === "claude-opus-4-6" ? "Claude Opus 4.6"
                              : "Gemini 2.5 Pro"
                            }
                          </span>
                        </div>

                        <div className="flex justify-center gap-6 text-sm text-slate-400 mt-2 mb-4">
                          <span className="flex items-center gap-1.5"><span className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></span>Jurista</span>
                          <span className="flex items-center gap-1.5"><span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse delay-150"></span>Auditor</span>
                          <span className="flex items-center gap-1.5"><span className="w-2 h-2 bg-green-400 rounded-full animate-pulse delay-300"></span>Cronista</span>
                        </div>
                        <p className="text-slate-400 text-sm text-center">Puedes cerrar esta página y volver más tarde</p>
                        <p className="text-slate-300 text-xs text-center mt-1">Recibirás un email al terminar</p>

                        {/* Panel diagnóstico en tiempo real */}
                        {diagLogs.length > 0 && (
                          <div className="mt-6">
                            <div className="flex items-center gap-2 mb-2">
                              <Terminal className="w-3.5 h-3.5 text-slate-400" />
                              <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Diagnóstico en vivo</span>
                              <span className="ml-auto text-xs text-emerald-500 flex items-center gap-1">
                                <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse"></span>
                                transmitiendo
                              </span>
                            </div>
                            <div
                              ref={logsPanelRef}
                              className="bg-slate-900 rounded-xl p-4 h-48 overflow-y-auto font-mono text-xs leading-relaxed"
                            >
                              {diagLogs.map((entry, i) => (
                                <div key={i} className={`mb-0.5 ${entry.nivel === "ERROR" ? "text-red-400" : (entry.msg ?? "").startsWith("✅") ? "text-emerald-400" : (entry.msg ?? "").startsWith("⚠️") ? "text-amber-400" : "text-slate-300"}`}>
                                  <span className="text-slate-600 mr-2 select-none">{new Date(entry.ts).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
                                  {entry.msg}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}

                {status === "done" && auditResult && (
                  <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
                    {/* Header con estado + botón PDF */}
                    <div className="bg-green-50 border-b border-green-100 px-6 py-4 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <CheckCircle2 className="w-5 h-5 text-green-600" />
                        <span className="font-semibold text-green-800">Auditoría completada</span>
                        {filename && <span className="text-xs text-slate-400 hidden sm:block">— {filename}</span>}
                      </div>
                      <button
                        onClick={downloadPdf}
                        disabled={pdfLoading}
                        className="flex items-center gap-2 bg-[#1e3a5f] hover:bg-[#152d4a] text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-60"
                      >
                        {pdfLoading
                          ? <Loader2 className="w-4 h-4 animate-spin" />
                          : <Download className="w-4 h-4" />
                        }
                        {pdfLoading ? "Generando..." : "Descargar PDF"}
                      </button>
                    </div>

                    {/* Pestañas */}
                    <div className="flex border-b border-slate-100">
                      <button
                        onClick={() => setActiveTab("informe")}
                        className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                          activeTab === "informe"
                            ? "border-blue-500 text-blue-700 bg-blue-50/50"
                            : "border-transparent text-slate-500 hover:text-slate-700"
                        }`}
                      >
                        <FileText className="w-4 h-4" />
                        Informe
                      </button>
                      <button
                        onClick={() => setActiveTab("diagnostico")}
                        className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                          activeTab === "diagnostico"
                            ? "border-slate-600 text-slate-800 bg-slate-50"
                            : "border-transparent text-slate-500 hover:text-slate-700"
                        }`}
                      >
                        <Terminal className="w-4 h-4" />
                        Diagnóstico técnico
                        {diagLogs.length > 0 && (
                          <span className="ml-1 bg-slate-200 text-slate-600 text-xs px-1.5 py-0.5 rounded-full">
                            {diagLogs.length}
                          </span>
                        )}
                      </button>
                    </div>

                    {/* Contenido de pestaña Informe */}
                    {activeTab === "informe" && (
                      <div className="p-6 sm:p-8" id="audit-report-print">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            h1: ({ children }) => <h1 className="text-2xl font-bold text-[#1e3a5f] mt-6 mb-3 pb-2 border-b border-slate-200">{children}</h1>,
                            h2: ({ children }) => <h2 className="text-xl font-semibold text-[#1e3a5f] mt-5 mb-2">{children}</h2>,
                            h3: ({ children }) => <h3 className="text-base font-semibold text-slate-700 mt-4 mb-1">{children}</h3>,
                            p:  ({ children }) => <p className="text-slate-700 text-sm leading-relaxed mb-3">{children}</p>,
                            ul: ({ children }) => <ul className="list-disc list-outside ml-5 mb-3 space-y-1">{children}</ul>,
                            ol: ({ children }) => <ol className="list-decimal list-outside ml-5 mb-3 space-y-1">{children}</ol>,
                            li: ({ children }) => <li className="text-slate-700 text-sm leading-relaxed">{children}</li>,
                            strong: ({ children }) => <strong className="font-semibold text-slate-800">{children}</strong>,
                            hr: () => <hr className="border-slate-200 my-5" />,
                            blockquote: ({ children }) => <blockquote className="border-l-4 border-blue-300 pl-4 italic text-slate-500 my-3">{children}</blockquote>,
                            code: ({ children }) => <code className="bg-slate-100 text-slate-700 text-xs px-1.5 py-0.5 rounded font-mono">{children}</code>,
                          }}
                        >
                          {auditResult}
                        </ReactMarkdown>
                      </div>
                    )}

                    {/* Contenido de pestaña Diagnóstico técnico */}
                    {activeTab === "diagnostico" && (
                      <div className="p-6">
                        <div className="flex items-center gap-2 mb-3">
                          <Terminal className="w-4 h-4 text-slate-500" />
                          <span className="text-sm font-medium text-slate-600">Log de ejecución</span>
                          <span className="ml-auto text-xs text-slate-400">{diagLogs.length} entradas</span>
                        </div>
                        {diagLogs.length === 0 ? (
                          <div className="bg-slate-900 rounded-xl p-6 text-center">
                            <p className="text-slate-500 text-sm font-mono">Sin logs disponibles para esta auditoría.</p>
                          </div>
                        ) : (
                          <div
                            ref={logsPanelRef}
                            className="bg-slate-900 rounded-xl p-4 h-[480px] overflow-y-auto font-mono text-xs leading-relaxed"
                          >
                            {diagLogs.map((entry, i) => (
                              <div
                                key={i}
                                className={`mb-0.5 ${
                                  entry.nivel === "ERROR"
                                    ? "text-red-400"
                                    : (entry.msg ?? "").startsWith("✅") || (entry.msg ?? "").startsWith("OK") || (entry.msg ?? "").includes("completad") || (entry.msg ?? "").includes("Completad")
                                      ? "text-emerald-400"
                                      : (entry.msg ?? "").startsWith("⚠️")
                                        ? "text-amber-400"
                                        : (entry.msg ?? "").startsWith("---") || (entry.msg ?? "").startsWith("===")
                                          ? "text-sky-300 font-semibold"
                                          : "text-slate-300"
                                }`}
                              >
                                <span className="text-slate-600 mr-2 select-none">
                                  {new Date(entry.ts).toLocaleTimeString("es-PE", {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                    second: "2-digit",
                                  })}
                                </span>
                                {entry.msg}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    <div className="px-6 sm:px-8 pb-6 border-t border-slate-50 pt-4">
                      <button onClick={reset} className="text-sm text-blue-600 hover:underline">
                        Auditar otro contrato
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Query mode */}
            {mode === "query" && (
              <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
                <div className="bg-[#1e3a5f] px-5 py-4">
                  <h3 className="font-semibold text-white flex items-center gap-2">
                    <MessageSquare className="w-4 h-4" />
                    Consulta sobre el contrato
                  </h3>
                </div>

                {/* Messages */}
                <div className="h-80 overflow-y-auto p-5 space-y-4">
                  {messages.length === 0 && (
                    <div className="text-center text-slate-400 text-sm py-8">
                      Haz tu primera pregunta sobre el contrato
                    </div>
                  )}
                  {messages.map((msg, i) => (
                    <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                      <div
                        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed
                          ${msg.role === "user"
                            ? "bg-[#1e3a5f] text-white rounded-br-sm"
                            : "bg-slate-100 text-slate-700 rounded-bl-sm"
                          }`}
                      >
                        {msg.text}
                      </div>
                    </div>
                  ))}
                  {queryLoading && (
                    <div className="flex justify-start">
                      <div className="bg-slate-100 rounded-2xl rounded-bl-sm px-4 py-3">
                        <Loader2 className="w-4 h-4 animate-spin text-slate-500" />
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <div className="border-t border-slate-100 p-4">
                  <form
                    onSubmit={(e) => { e.preventDefault(); sendQuestion(); }}
                    className="flex gap-3"
                  >
                    <input
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      placeholder="Ej: ¿Cuáles son las penalidades por incumplimiento?"
                      className="flex-1 border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                    />
                    <button
                      type="submit"
                      disabled={!question.trim() || queryLoading}
                      className="bg-[#1e3a5f] hover:bg-[#152d4a] text-white p-3 rounded-xl transition-colors disabled:opacity-50"
                    >
                      <Send className="w-5 h-5" />
                    </button>
                  </form>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function AuditPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-50 flex items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>}>
      <AuditContent />
    </Suspense>
  );
}
