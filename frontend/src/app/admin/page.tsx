"use client";
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { adminAPI } from "@/lib/api";
import Navbar from "@/components/Navbar";
import {
  Shield,
  Users,
  Loader2,
  CheckCircle2,
  XCircle,
  RefreshCw,
  ChevronDown,
} from "lucide-react";

interface UserRow {
  id: number;
  nombre: string;
  email: string;
  rol: string;
  activo: boolean;
  creado_en: string;
}

const ROLES = ["pendiente", "basico", "auditor", "admin"];
const ROL_COLORS: Record<string, string> = {
  pendiente: "bg-yellow-100 text-yellow-700",
  basico:    "bg-slate-100 text-slate-600",
  auditor:   "bg-blue-100 text-blue-700",
  admin:     "bg-purple-100 text-purple-700",
};

export default function AdminPage() {
  const { isAdmin, isAuthenticated } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<{ id: number; msg: string } | null>(null);

  useEffect(() => {
    if (!isAuthenticated) { router.push("/login"); return; }
    if (!isAdmin) { router.push("/dashboard"); return; }
  }, [isAuthenticated, isAdmin, router]);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminAPI.getUsers();
      setUsers(res.data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const changeRole = async (userId: number, role: string) => {
    setActionLoading(userId);
    try {
      await adminAPI.changeRole({ user_id: userId, nuevo_rol: role });
      setUsers((prev) => prev.map((u) => u.id === userId ? { ...u, rol: role } : u));
      setFeedback({ id: userId, msg: `Rol cambiado a ${role}` });
      setTimeout(() => setFeedback(null), 2000);
    } catch {
      setFeedback({ id: userId, msg: "Error al cambiar rol" });
      setTimeout(() => setFeedback(null), 2000);
    } finally {
      setActionLoading(null);
    }
  };

  const toggleActive = async (user: UserRow) => {
    setActionLoading(user.id);
    try {
      if (user.activo) {
        await adminAPI.suspend(user.id);
        setUsers((prev) => prev.map((u) => u.id === user.id ? { ...u, activo: false } : u));
      } else {
        await adminAPI.activate(user.id);
        setUsers((prev) => prev.map((u) => u.id === user.id ? { ...u, activo: true } : u));
      }
    } catch {
      // silent
    } finally {
      setActionLoading(null);
    }
  };

  if (!isAdmin) return null;

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="max-w-7xl mx-auto px-4 py-10">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <Shield className="w-7 h-7 text-purple-600" />
            <div>
              <h1 className="text-2xl font-bold text-[#1e3a5f]">Panel de Administración</h1>
              <p className="text-slate-500 text-sm mt-0.5">Gestión de usuarios y roles</p>
            </div>
          </div>
          <button
            onClick={fetchUsers}
            className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 bg-white border border-slate-200 px-4 py-2 rounded-lg shadow-sm hover:shadow transition-all"
          >
            <RefreshCw className="w-4 h-4" />
            Actualizar
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {ROLES.map((rol) => (
            <div key={rol} className="bg-white rounded-2xl border border-slate-100 shadow-card p-5">
              <div className="text-2xl font-bold text-[#1e3a5f]">
                {users.filter((u) => u.rol === rol).length}
              </div>
              <div className={`text-xs font-semibold mt-1 px-2 py-0.5 rounded-full inline-block ${ROL_COLORS[rol]}`}>
                {rol}
              </div>
            </div>
          ))}
        </div>

        {/* Table */}
        <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
          <div className="border-b border-slate-100 px-6 py-4 flex items-center gap-2">
            <Users className="w-5 h-5 text-slate-400" />
            <span className="font-semibold text-[#1e3a5f]">Usuarios ({users.length})</span>
          </div>

          {loading ? (
            <div className="py-16 text-center">
              <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
                    <th className="px-6 py-3 text-left font-medium">Usuario</th>
                    <th className="px-6 py-3 text-left font-medium">Correo</th>
                    <th className="px-6 py-3 text-left font-medium">Rol</th>
                    <th className="px-6 py-3 text-left font-medium">Estado</th>
                    <th className="px-6 py-3 text-left font-medium">Registrado</th>
                    <th className="px-6 py-3 text-left font-medium">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {users.map((user) => (
                    <tr key={user.id} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-6 py-4 font-medium text-[#1e3a5f]">{user.nombre}</td>
                      <td className="px-6 py-4 text-slate-500">{user.email}</td>
                      <td className="px-6 py-4">
                        <div className="relative inline-block">
                          <select
                            value={user.rol}
                            onChange={(e) => changeRole(user.id, e.target.value)}
                            disabled={actionLoading === user.id}
                            className={`appearance-none pl-3 pr-7 py-1.5 rounded-full text-xs font-semibold border-0 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-400 ${ROL_COLORS[user.rol]}`}
                          >
                            {ROLES.map((r) => (
                              <option key={r} value={r}>{r}</option>
                            ))}
                          </select>
                          <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 w-3 h-3 pointer-events-none" />
                        </div>
                        {feedback?.id === user.id && (
                          <span className="ml-2 text-xs text-green-600">{feedback.msg}</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <span className={`flex items-center gap-1.5 text-xs font-medium ${user.activo ? "text-green-600" : "text-red-500"}`}>
                          {user.activo
                            ? <><CheckCircle2 className="w-4 h-4" /> Activo</>
                            : <><XCircle className="w-4 h-4" /> Suspendido</>
                          }
                        </span>
                      </td>
                      <td className="px-6 py-4 text-slate-400 text-xs">
                        {user.creado_en ? new Date(user.creado_en).toLocaleDateString("es-PE") : "-"}
                      </td>
                      <td className="px-6 py-4">
                        <button
                          onClick={() => toggleActive(user)}
                          disabled={actionLoading === user.id}
                          className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50
                            ${user.activo
                              ? "text-red-600 hover:bg-red-50 border border-red-200"
                              : "text-green-600 hover:bg-green-50 border border-green-200"
                            }`}
                        >
                          {actionLoading === user.id ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : user.activo ? "Suspender" : "Activar"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
