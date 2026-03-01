import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";

export const metadata: Metadata = {
  title: "ContractIA — Auditoría Inteligente de Contratos",
  description:
    "Plataforma de auditoría legal inteligente impulsada por IA. Analiza contratos, identifica riesgos y obtén recomendaciones expertas.",
  keywords: "contratos, auditoría, inteligencia artificial, legal, peru",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
