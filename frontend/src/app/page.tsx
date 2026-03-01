"use client";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import {
  FileSearch,
  ShieldCheck,
  Zap,
  Bot,
  ChevronRight,
  CheckCircle2,
  Scale,
  Clock,
} from "lucide-react";

const features = [
  {
    icon: FileSearch,
    title: "Análisis profundo de contratos",
    desc: "Nuestros agentes de IA revisan cláusulas, obligaciones y riesgos legales con precisión experta.",
  },
  {
    icon: ShieldCheck,
    title: "Detección de riesgos",
    desc: "Identifica cláusulas abusivas, plazos críticos y condiciones desfavorables antes de firmar.",
  },
  {
    icon: Zap,
    title: "Resultados en minutos",
    desc: "Lo que a un abogado le tomaría horas, ContractIA lo entrega en minutos con informes detallados.",
  },
  {
    icon: Bot,
    title: "Consulta interactiva",
    desc: "Haz preguntas específicas sobre tu contrato y obtén respuestas claras y fundamentadas.",
  },
  {
    icon: Scale,
    title: "Perspectiva legal peruana",
    desc: "Análisis contextualizado con normativa peruana: Código Civil, Ley de Contrataciones del Estado y más.",
  },
  {
    icon: Clock,
    title: "Disponible 24/7",
    desc: "Accede desde la web o Telegram cuando lo necesites, sin esperar citas ni horarios de oficina.",
  },
];

const steps = [
  { num: "01", title: "Crea tu cuenta", desc: "Regístrate con tu correo y verifica tu identidad en segundos." },
  { num: "02", title: "Sube tu contrato", desc: "Carga tu PDF o Word directamente en la plataforma." },
  { num: "03", title: "Inicia la auditoría", desc: "Nuestros 3 agentes especializados analizan el contrato en paralelo." },
  { num: "04", title: "Revisa el informe", desc: "Recibe un análisis completo con riesgos, hallazgos y recomendaciones." },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />

      {/* Hero */}
      <section className="bg-gradient-to-br from-[#1e3a5f] via-[#1a3255] to-[#0f2040] text-white py-24 px-4">
        <div className="max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-white/10 text-blue-200 text-sm font-medium px-4 py-2 rounded-full mb-6 backdrop-blur-sm border border-white/10">
            <Bot className="w-4 h-4" />
            Impulsado por Gemini 2.5 Pro + Multi-Agentes IA
          </div>
          <h1 className="text-4xl md:text-6xl font-bold leading-tight mb-6 tracking-tight">
            Auditoría inteligente<br />
            <span className="text-blue-300">de contratos</span>
          </h1>
          <p className="text-lg md:text-xl text-white/75 max-w-2xl mx-auto mb-10 leading-relaxed">
            ContractIA analiza tus contratos con IA avanzada, detecta riesgos legales y
            te entrega recomendaciones claras en minutos.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/register"
              className="inline-flex items-center gap-2 bg-blue-500 hover:bg-blue-600 text-white font-semibold px-8 py-4 rounded-xl transition-all shadow-lg hover:shadow-blue-500/30 text-lg"
            >
              Comenzar gratis
              <ChevronRight className="w-5 h-5" />
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 bg-white/10 hover:bg-white/20 text-white font-semibold px-8 py-4 rounded-xl transition-all border border-white/20 text-lg backdrop-blur-sm"
            >
              Iniciar sesión
            </Link>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="bg-white border-b border-slate-100">
        <div className="max-w-5xl mx-auto px-4 py-10 grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
          {[
            { value: "3", label: "Agentes IA especializados" },
            { value: "< 5 min", label: "Tiempo de auditoría" },
            { value: "100%", label: "Privacidad garantizada" },
            { value: "24/7", label: "Disponibilidad" },
          ].map((s) => (
            <div key={s.label}>
              <div className="text-3xl font-bold text-[#1e3a5f] mb-1">{s.value}</div>
              <div className="text-sm text-slate-500">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold text-[#1e3a5f] mb-4">
              Todo lo que necesitas para revisar contratos
            </h2>
            <p className="text-slate-500 text-lg max-w-2xl mx-auto">
              Una plataforma completa que combina múltiples perspectivas legales en un solo análisis.
            </p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="bg-white rounded-2xl p-6 shadow-card hover:shadow-card-hover transition-shadow border border-slate-100">
                <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
                  <Icon className="w-6 h-6 text-blue-600" />
                </div>
                <h3 className="font-semibold text-[#1e3a5f] text-lg mb-2">{title}</h3>
                <p className="text-slate-500 text-sm leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-[#1e3a5f] text-white py-20 px-4">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">¿Cómo funciona?</h2>
            <p className="text-white/60 text-lg">4 pasos simples para auditar tu contrato</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {steps.map((step) => (
              <div key={step.num} className="bg-white/5 rounded-2xl p-6 border border-white/10">
                <div className="text-4xl font-bold text-blue-300/50 mb-3">{step.num}</div>
                <h3 className="font-semibold text-lg mb-2">{step.title}</h3>
                <p className="text-white/60 text-sm leading-relaxed">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Agents */}
      <section className="py-20 px-4 bg-white">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold text-[#1e3a5f] mb-4">
            Sistema multi-agente
          </h2>
          <p className="text-slate-500 text-lg mb-12 max-w-2xl mx-auto">
            Tres agentes especializados analizan tu contrato desde diferentes perspectivas.
          </p>
          <div className="grid md:grid-cols-3 gap-6">
            {[
              { name: "Jurista", emoji: "⚖️", desc: "Analiza el marco legal aplicable e identifica cláusulas problemáticas desde la perspectiva del derecho." },
              { name: "Auditor", emoji: "🔍", desc: "Examina los riesgos contractuales, penalidades, plazos y condiciones desfavorables para el contratante." },
              { name: "Cronista", emoji: "📋", desc: "Documenta los hallazgos, sintetiza el análisis y genera el informe final estructurado." },
            ].map((agent) => (
              <div key={agent.name} className="bg-slate-50 rounded-2xl p-6 border border-slate-100">
                <div className="text-4xl mb-4">{agent.emoji}</div>
                <h3 className="font-bold text-[#1e3a5f] text-xl mb-2">Agente {agent.name}</h3>
                <p className="text-slate-500 text-sm leading-relaxed">{agent.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-gradient-to-r from-blue-600 to-blue-700 text-white py-16 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Empieza a auditar tus contratos hoy
          </h2>
          <p className="text-blue-100 text-lg mb-8">
            Regístrate gratis y sube tu primer contrato en menos de 2 minutos.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Link
              href="/register"
              className="inline-flex items-center gap-2 bg-white text-blue-700 font-bold px-8 py-4 rounded-xl hover:bg-blue-50 transition-colors shadow-lg text-lg"
            >
              Crear cuenta gratuita
              <ChevronRight className="w-5 h-5" />
            </Link>
            <div className="flex items-center gap-2 text-blue-100 text-sm">
              <CheckCircle2 className="w-5 h-5 text-blue-200" />
              Sin tarjeta de crédito requerida
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-[#0f2040] text-white/50 py-8 px-4 text-center text-sm">
        <p>© 2025 ContractIA — Sistema de auditoría inteligente de contratos</p>
        <p className="mt-1">Desarrollado con IA generativa · Gemini 2.5 Pro · LangChain</p>
      </footer>
    </div>
  );
}
