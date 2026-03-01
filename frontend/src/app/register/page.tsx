"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authAPI, extractError } from "@/lib/api";
import { FileText, Loader2, CheckCircle2, Mail } from "lucide-react";

type Step = "form" | "otp" | "done";

export default function RegisterPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("form");
  const [email, setEmail] = useState("");
  const [codigo, setCodigo] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authAPI.register({ email });
      setStep("otp");
    } catch (err) {
      setError(extractError(err, "Error al registrar. Intenta nuevamente."));
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authAPI.verify({ email, codigo });
      setStep("done");
      setTimeout(() => router.push("/login"), 3000);
    } catch (err) {
      setError(extractError(err, "Código inválido o expirado."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center px-4">
      <Link href="/" className="flex items-center gap-2 font-bold text-2xl text-[#1e3a5f] mb-8">
        <FileText className="w-7 h-7 text-blue-500" />
        Contract<span className="text-blue-500">IA</span>
      </Link>

      <div className="bg-white rounded-2xl shadow-card w-full max-w-md p-8">
        {step === "done" ? (
          <div className="text-center py-4">
            <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-[#1e3a5f] mb-2">¡Cuenta creada!</h2>
            <p className="text-slate-500 text-sm leading-relaxed">
              Te hemos enviado tu contraseña a <strong>{email}</strong>.<br />
              Un administrador aprobará tu cuenta y podrás ingresar.
              <br /><br />Redirigiendo al login...
            </p>
          </div>

        ) : step === "otp" ? (
          <>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center">
                <Mail className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-[#1e3a5f]">Verifica tu correo</h1>
                <p className="text-slate-500 text-xs mt-0.5">Código enviado a <strong>{email}</strong></p>
              </div>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm mb-4">
                {error}
              </div>
            )}

            <form onSubmit={handleVerify} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Código de verificación
                </label>
                <input
                  type="text"
                  value={codigo}
                  onChange={(e) => setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="123456"
                  maxLength={6}
                  required
                  className="w-full border border-slate-200 rounded-lg px-4 py-3 text-center text-2xl font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                />
              </div>
              <button
                type="submit"
                disabled={loading || codigo.length !== 6}
                className="w-full bg-[#1e3a5f] hover:bg-[#152d4a] text-white font-semibold py-3 rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-60"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                Verificar código
              </button>
              <button
                type="button"
                onClick={() => setStep("form")}
                className="w-full text-sm text-slate-500 hover:text-slate-700"
              >
                Cambiar email
              </button>
            </form>
          </>

        ) : (
          <>
            <h1 className="text-2xl font-bold text-[#1e3a5f] mb-1">Crear cuenta</h1>
            <p className="text-slate-500 text-sm mb-6">
              Ingresa tu correo y te enviaremos un código de verificación.
              Tu contraseña será generada automáticamente.
            </p>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm mb-4">
                {error}
              </div>
            )}

            <form onSubmit={handleRegister} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Correo electrónico
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="tu@correo.com"
                  required
                  className="w-full border border-slate-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-[#1e3a5f] hover:bg-[#152d4a] text-white font-semibold py-3 rounded-lg transition-colors flex items-center justify-center gap-2 mt-2 disabled:opacity-60"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {loading ? "Enviando código..." : "Continuar"}
              </button>
            </form>

            <p className="text-center text-sm text-slate-500 mt-6">
              ¿Ya tienes cuenta?{" "}
              <Link href="/login" className="text-blue-600 hover:underline font-medium">
                Iniciar sesión
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
