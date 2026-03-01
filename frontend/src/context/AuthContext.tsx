"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from "react";
import Cookies from "js-cookie";
import { jwtDecode } from "jwt-decode";

interface JWTPayload {
  sub: string;
  email: string;
  rol: string;
  exp: number;
}

interface AuthContextType {
  user: JWTPayload | null;
  token: string | null;
  login: (token: string) => void;
  logout: () => void;
  isAdmin: boolean;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType>({} as AuthContextType);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<JWTPayload | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    const saved = Cookies.get("token");
    if (saved) {
      try {
        const decoded = jwtDecode<JWTPayload>(saved);
        if (decoded.exp * 1000 > Date.now()) {
          setToken(saved);
          setUser(decoded);
        } else {
          Cookies.remove("token");
        }
      } catch {
        Cookies.remove("token");
      }
    }
  }, []);

  const login = (newToken: string) => {
    Cookies.set("token", newToken, { expires: 1, sameSite: "strict" });
    const decoded = jwtDecode<JWTPayload>(newToken);
    setToken(newToken);
    setUser(decoded);
  };

  const logout = () => {
    Cookies.remove("token");
    setToken(null);
    setUser(null);
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        login,
        logout,
        isAdmin: user?.rol === "admin",
        isAuthenticated: !!user,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
