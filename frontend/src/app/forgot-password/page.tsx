"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authAPI, extractError } from "@/lib/api";
import { FileText, Loader2, CheckCircle2, Eye, EyeOff } from "lucide-react";

type Step = "email" | "reset" | "done";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [codigo, setCodigo] = useState("");
  const [nuevaPassword, setNuevaPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authAPI.forgotPassword({ email });
      setStep("reset");
    } catch (err) {
      setError(extractError(err, "Error al enviar el código."));
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (nuevaPassword.length < 8) {
      setError("La contraseña debe tener al menos 8 caracteres.");
      return;
    }
    setLoading(true);
    try {
      await authAPI.resetPassword({ email, codigo, nueva_password: nuevaPassword });
      setStep("done");
      setTimeout(() => router.push("/login"), 2500);
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
            <h2 className="text-2xl font-bold text-[#1e3a5f] mb-2">¡Contraseña actualizada!</h2>
            <p className="text-slate-500 text-sm">Redirigiendo al login...</p>
          </div>

        ) : step === "reset" ? (
          <>
            <h1 className="text-2xl font-bold text-[#1e3a5f] mb-1">Nueva contraseña</h1>
            <p className="text-slate-500 text-sm mb-6">
              Ingresa el código enviado a <strong>{email}</strong> y tu nueva contraseña.
            </p>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm mb-4">
                {error}
              </div>
            )}

            <form onSubmit={handleReset} className="space-y-4">
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
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Nueva contraseña
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    value={nuevaPassword}
                    onChange={(e) => setNuevaPassword(e.target.value)}
                    placeholder="Mínimo 8 caracteres"
                    minLength={8}
                    required
                    className="w-full border border-slate-200 rounded-lg px-4 py-3 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <button
                type="submit"
                disabled={loading || codigo.length !== 6}
                className="w-full bg-[#1e3a5f] hover:bg-[#152d4a] text-white font-semibold py-3 rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-60"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                Actualizar contraseña
              </button>
              <button
                type="button"
                onClick={() => setStep("email")}
                className="w-full text-sm text-slate-500 hover:text-slate-700"
              >
                Cambiar email
              </button>
            </form>
          </>

        ) : (
          <>
            <h1 className="text-2xl font-bold text-[#1e3a5f] mb-1">¿Olvidaste tu contraseña?</h1>
            <p className="text-slate-500 text-sm mb-6">
              Ingresa tu correo y te enviaremos un código para crear una nueva contraseña.
            </p>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm mb-4">
                {error}
              </div>
            )}

            <form onSubmit={handleSendCode} className="space-y-4">
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
                className="w-full bg-[#1e3a5f] hover:bg-[#152d4a] text-white font-semibold py-3 rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-60"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {loading ? "Enviando..." : "Enviar código"}
              </button>
            </form>

            <p className="text-center text-sm text-slate-500 mt-6">
              <Link href="/login" className="text-blue-600 hover:underline font-medium">
                Volver al login
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
