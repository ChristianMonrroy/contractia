"use client";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import {
  FileSearch,
  MessageSquare,
  Shield,
  User,
  ChevronRight,
  Clock,
  AlertCircle,
} from "lucide-react";

const ROLE_LABELS: Record<string, { label: string; color: string }> = {
  pendiente: { label: "Pendiente de aprobación", color: "text-yellow-600 bg-yellow-50 border-yellow-200" },
  basico:    { label: "Básico", color: "text-slate-600 bg-slate-100 border-slate-200" },
  auditor:   { label: "Auditor", color: "text-blue-700 bg-blue-50 border-blue-200" },
  admin:     { label: "Administrador", color: "text-purple-700 bg-purple-50 border-purple-200" },
};

const ROLE_LIMITS: Record<string, string> = {
  pendiente: "Acceso restringido hasta aprobación",
  basico:    "10 consultas disponibles",
  auditor:   "3 auditorías · 30 consultas",
  admin:     "Acceso ilimitado",
};

export default function DashboardPage() {
  const { user, isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated) router.push("/login");
  }, [isAuthenticated, router]);

  if (!user) return null;

  const roleInfo = ROLE_LABELS[user.rol] || ROLE_LABELS["basico"];
  const isPending = user.rol === "pendiente";

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="max-w-6xl mx-auto px-4 py-10">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-[#1e3a5f]">
            Hola, {user.sub} 👋
          </h1>
          <p className="text-slate-500 mt-1">Bienvenido a tu panel de control</p>
        </div>

        {/* Pending alert */}
        {isPending && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-2xl p-5 mb-6 flex items-start gap-4">
            <Clock className="w-6 h-6 text-yellow-500 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="font-semibold text-yellow-800 mb-1">Tu cuenta está pendiente de aprobación</h3>
              <p className="text-yellow-700 text-sm">
                Un administrador revisará tu solicitud y te asignará un rol.
                Recibirás una notificación cuando sea aprobada.
              </p>
            </div>
          </div>
        )}

        {/* User card */}
        <div className="bg-white rounded-2xl shadow-card border border-slate-100 p-6 mb-6">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 bg-[#1e3a5f] rounded-2xl flex items-center justify-center">
                <User className="w-7 h-7 text-white" />
              </div>
              <div>
                <h2 className="font-semibold text-[#1e3a5f] text-lg">{user.sub}</h2>
                <p className="text-slate-500 text-sm">{user.email}</p>
              </div>
            </div>
            <span className={`text-xs font-semibold px-3 py-1.5 rounded-full border ${roleInfo.color}`}>
              {roleInfo.label}
            </span>
          </div>
          <div className="mt-4 pt-4 border-t border-slate-100 flex items-center gap-2 text-sm text-slate-500">
            <AlertCircle className="w-4 h-4" />
            {ROLE_LIMITS[user.rol]}
          </div>
        </div>

        {/* Actions */}
        <h2 className="text-lg font-semibold text-[#1e3a5f] mb-4">Acciones disponibles</h2>
        <div className="grid md:grid-cols-2 gap-4">
          <ActionCard
            icon={FileSearch}
            title="Nueva auditoría"
            desc="Sube un contrato PDF o Word y obtén un análisis completo con riesgos y recomendaciones."
            href="/audit"
            disabled={isPending}
            badge="Auditor / Admin"
          />
          <ActionCard
            icon={MessageSquare}
            title="Consulta interactiva"
            desc="Sube un contrato y haz preguntas específicas sobre su contenido."
            href="/audit?mode=query"
            disabled={isPending}
            badge="Basico+"
          />
          <ActionCard
            icon={Shield}
            title="Panel de administración"
            desc="Gestiona usuarios, roles y monitorea el uso del sistema."
            href="/admin"
            disabled={user.rol !== "admin"}
            badge="Solo Admin"
          />
        </div>
      </div>
    </div>
  );
}

function ActionCard({
  icon: Icon,
  title,
  desc,
  href,
  disabled,
  badge,
}: {
  icon: React.ElementType;
  title: string;
  desc: string;
  href: string;
  disabled: boolean;
  badge?: string;
}) {
  const content = (
    <div
      className={`bg-white rounded-2xl border p-6 transition-all flex items-start gap-4 group
        ${disabled
          ? "border-slate-100 opacity-50 cursor-not-allowed"
          : "border-slate-100 shadow-card hover:shadow-card-hover hover:border-blue-100 cursor-pointer"
        }`}
    >
      <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0
        ${disabled ? "bg-slate-100" : "bg-blue-50 group-hover:bg-blue-100 transition-colors"}`}>
        <Icon className={`w-6 h-6 ${disabled ? "text-slate-400" : "text-blue-600"}`} />
      </div>
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold text-[#1e3a5f]">{title}</h3>
          {!disabled && <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-blue-500 transition-colors" />}
        </div>
        <p className="text-slate-500 text-sm leading-relaxed">{desc}</p>
        {badge && (
          <span className="inline-block mt-2 text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
            {badge}
          </span>
        )}
      </div>
    </div>
  );

  return disabled ? <div>{content}</div> : <Link href={href}>{content}</Link>;
}
