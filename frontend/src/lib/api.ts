import axios from "axios";
import Cookies from "js-cookie";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  "https://contractia-api-444429430547.us-central1.run.app";

const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// Inyectar token JWT en cada request
api.interceptors.request.use((config) => {
  const token = Cookies.get("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Redirigir a login si 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      Cookies.remove("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// Extrae mensaje de error de FastAPI (string o array de Pydantic)
export function extractError(err: unknown, fallback = "Error desconocido"): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg).join(", ");
  return fallback;
}

// --- Auth ---
export const authAPI = {
  register: (data: { email: string }) =>
    api.post("/auth/register", data),

  verify: (data: { email: string; codigo: string }) =>
    api.post("/auth/verify", data),

  login: (data: { email: string; password: string }) =>
    api.post<{ access_token: string; token_type: string }>("/auth/login", data),

  forgotPassword: (data: { email: string }) =>
    api.post("/auth/forgot-password", data),

  resetPassword: (data: { email: string; codigo: string; nueva_password: string }) =>
    api.post("/auth/reset-password", data),
};

// --- Contratos ---
export const contractsAPI = {
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<{ session_id: string; filename: string; chunks: number }>(
      "/contracts/upload",
      form,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
  },

  query: (data: { session_id: string; pregunta: string }) =>
    api.post<{ respuesta: string }>("/contracts/query", data),

  audit: (data: { session_id: string }) =>
    api.post<{ audit_id: string; message: string }>("/contracts/audit", data),

  getAudit: (audit_id: string) =>
    api.get<{ audit_id: string; status: string; result?: string }>(
      `/contracts/audit/${audit_id}`
    ),
};

// --- Admin ---
export const adminAPI = {
  getUsers: () => api.get("/admin/usuarios"),
  changeRole: (data: { user_id: number; nuevo_rol: string }) =>
    api.patch("/admin/usuarios/rol", data),
  suspend: (id: number) => api.patch(`/admin/usuarios/${id}/suspender`),
  activate: (id: number) => api.patch(`/admin/usuarios/${id}/activar`),

  getActividad: (params?: {
    telegram_id?: number;
    fecha_inicio?: string;
    fecha_fin?: string;
    accion?: string;
  }) => api.get<ActividadRow[]>("/admin/actividad", { params }),

  getResumenActividad: () =>
    api.get<ResumenActividad>("/admin/actividad/resumen"),
};

export interface ActividadRow {
  id: number;
  telegram_id: number;
  email: string;
  rol: string;
  accion: string;
  canal: string;
  detalle: string;
  duracion_segundos: number | null;
  n_hallazgos: number | null;
  timestamp: string;
}

export interface ResumenActividad {
  total_auditorias: number;
  total_preguntas: number;
  duracion_promedio_auditoria: number | null;
  duracion_promedio_pregunta: number | null;
  top_usuarios: Array<{ email: string; total: number }>;
}
