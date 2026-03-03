"use client";
import { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { contractsAPI, extractError } from "@/lib/api";
import Navbar from "@/components/Navbar";
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
} from "lucide-react";

type Mode = "audit" | "query";
type AuditStatus = "idle" | "uploading" | "ready" | "running" | "done" | "error";

function AuditContent() {
  const { isAuthenticated } = useAuth();
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
  const [progressPct, setProgressPct] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!isAuthenticated) router.push("/login");
  }, [isAuthenticated, router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

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
      const res = await contractsAPI.upload(file);
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
      const res = await contractsAPI.audit(uploadedFile);
      const auditId = res.data.audit_id;
      const poll = setInterval(async () => {
        try {
          const check = await contractsAPI.getAudit(auditId);
          if (check.data.progress_msg) setProgressMsg(check.data.progress_msg);
          if (check.data.progress_pct != null) setProgressPct(check.data.progress_pct);
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

  const sendQuestion = async () => {
    if (!question.trim() || !sessionId || queryLoading) return;
    const q = question.trim();
    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setQuestion("");
    setQueryLoading(true);
    try {
      const res = await contractsAPI.query({ session_id: sessionId, pregunta: q });
      setMessages((prev) => [...prev, { role: "ai", text: res.data.respuesta }]);
    } catch {
      setMessages((prev) => [...prev, { role: "ai", text: "❌ Error al procesar la pregunta." }]);
    } finally {
      setQueryLoading(false);
    }
  };

  const reset = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setStatus("idle");
    setSessionId("");
    setUploadedFile(null);
    setFilename("");
    setAuditResult("");
    setMessages([]);
    setError("");
    setProgressMsg("");
    setProgressPct(0);
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
            <Loader2 className="w-10 h-10 text-blue-500 animate-spin mx-auto mb-4" />
            <p className="text-slate-600 font-medium">Procesando y vectorizando el contrato...</p>
            <p className="text-slate-400 text-sm mt-1">Esto puede tomar unos segundos</p>
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
                      {mode === "audit" ? "Listo para auditar" : "Contrato indexado correctamente"}
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
                  <div className="text-center">
                    {error && (
                      <div className="bg-amber-50 border border-amber-200 text-amber-700 rounded-xl px-4 py-3 text-sm mb-4 flex items-center gap-2 justify-center">
                        <AlertCircle className="w-4 h-4" />
                        {error}
                      </div>
                    )}
                    <button
                      onClick={startAudit}
                      disabled={!uploadedFile}
                      className="bg-[#1e3a5f] hover:bg-[#152d4a] text-white font-semibold px-8 py-4 rounded-xl transition-colors inline-flex items-center gap-2 text-lg shadow-lg disabled:opacity-50"
                    >
                      <FileSearch className="w-5 h-5" />
                      Iniciar auditoría completa
                    </button>
                    <p className="text-slate-400 text-sm mt-3">
                      Los 3 agentes IA analizarán tu contrato (≈ 3-5 min)
                    </p>
                    <p className="text-slate-400 text-xs mt-1">
                      Puedes cerrar esta página — recibirás un email cuando termine
                    </p>
                  </div>
                )}

                {status === "running" && (
                  <div className="bg-white rounded-2xl border border-slate-100 shadow-card p-10">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-semibold text-[#1e3a5f] text-lg">Auditoría en progreso</h3>
                      <span className="text-2xl font-bold text-blue-600 tabular-nums">{progressPct}%</span>
                    </div>

                    {/* Barra de progreso */}
                    <div className="w-full bg-slate-100 rounded-full h-3 overflow-hidden mb-3">
                      <div
                        className="h-3 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 transition-all duration-700 ease-out"
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>

                    {progressMsg && (
                      <p className="text-blue-600 font-medium text-sm mb-4">{progressMsg}</p>
                    )}

                    <div className="flex justify-center gap-6 text-sm text-slate-400 mt-4 mb-4">
                      <span className="flex items-center gap-1.5"><span className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></span>Jurista</span>
                      <span className="flex items-center gap-1.5"><span className="w-2 h-2 bg-purple-400 rounded-full animate-pulse delay-150"></span>Auditor</span>
                      <span className="flex items-center gap-1.5"><span className="w-2 h-2 bg-green-400 rounded-full animate-pulse delay-300"></span>Cronista</span>
                    </div>
                    <p className="text-slate-400 text-sm text-center">Puedes cerrar esta página y volver más tarde</p>
                    <p className="text-slate-300 text-xs text-center mt-1">Recibirás un email al terminar</p>
                  </div>
                )}

                {status === "done" && auditResult && (
                  <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
                    <div className="bg-green-50 border-b border-green-100 px-6 py-4 flex items-center gap-3">
                      <CheckCircle2 className="w-5 h-5 text-green-600" />
                      <span className="font-semibold text-green-800">Auditoría completada</span>
                    </div>
                    <div className="p-6">
                      <pre className="whitespace-pre-wrap text-sm text-slate-700 leading-relaxed font-sans">
                        {auditResult}
                      </pre>
                    </div>
                    <div className="px-6 pb-6">
                      <button
                        onClick={reset}
                        className="text-sm text-blue-600 hover:underline"
                      >
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
