"use client";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { useState } from "react";
import { FileText, Menu, X, LogOut, LayoutDashboard, Shield } from "lucide-react";

export default function Navbar() {
  const { isAuthenticated, isAdmin, user, logout } = useAuth();
  const [open, setOpen] = useState(false);

  return (
    <nav className="bg-[#1e3a5f] text-white shadow-lg sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 font-bold text-xl tracking-tight">
            <FileText className="w-6 h-6 text-blue-300" />
            <span>Contract<span className="text-blue-300">IA</span></span>
          </Link>

          {/* Desktop nav */}
          <div className="hidden md:flex items-center gap-6 text-sm font-medium">
            {isAuthenticated ? (
              <>
                <Link href="/dashboard" className="flex items-center gap-1.5 hover:text-blue-300 transition-colors">
                  <LayoutDashboard className="w-4 h-4" />
                  Dashboard
                </Link>
                {isAdmin && (
                  <Link href="/admin" className="flex items-center gap-1.5 hover:text-blue-300 transition-colors">
                    <Shield className="w-4 h-4" />
                    Admin
                  </Link>
                )}
                <div className="flex items-center gap-3 ml-2 pl-4 border-l border-white/20">
                  <span className="text-white/70 text-xs">{user?.email}</span>
                  <button
                    onClick={logout}
                    className="flex items-center gap-1.5 bg-white/10 hover:bg-white/20 px-3 py-1.5 rounded-md transition-colors"
                  >
                    <LogOut className="w-4 h-4" />
                    Salir
                  </button>
                </div>
              </>
            ) : (
              <>
                <Link href="/login" className="hover:text-blue-300 transition-colors">
                  Iniciar sesión
                </Link>
                <Link
                  href="/register"
                  className="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg transition-colors font-semibold"
                >
                  Registrarse
                </Link>
              </>
            )}
          </div>

          {/* Mobile hamburger */}
          <button className="md:hidden p-2" onClick={() => setOpen(!open)}>
            {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="md:hidden bg-[#152d4a] px-4 py-4 space-y-3 text-sm">
          {isAuthenticated ? (
            <>
              <Link href="/dashboard" className="block py-2 hover:text-blue-300" onClick={() => setOpen(false)}>Dashboard</Link>
              {isAdmin && <Link href="/admin" className="block py-2 hover:text-blue-300" onClick={() => setOpen(false)}>Admin</Link>}
              <button onClick={logout} className="block w-full text-left py-2 text-red-300 hover:text-red-200">Cerrar sesión</button>
            </>
          ) : (
            <>
              <Link href="/login" className="block py-2 hover:text-blue-300" onClick={() => setOpen(false)}>Iniciar sesión</Link>
              <Link href="/register" className="block py-2 text-blue-300 font-semibold" onClick={() => setOpen(false)}>Registrarse</Link>
            </>
          )}
        </div>
      )}
    </nav>
  );
}
