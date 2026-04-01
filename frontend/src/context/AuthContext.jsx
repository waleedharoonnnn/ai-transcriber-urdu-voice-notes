import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { api, setAccessToken } from "../api/api";

const AuthContext = createContext(null);

const STORAGE_KEY = "auth_session";

function normalizeSession(session) {
  if (!session || typeof session !== "object") return null;

  // New normalized shape:
  // { access_token: string|null, user: { id: string, email?: string } }
  if (session.user && session.user.id) {
    return {
      access_token: session.access_token || null,
      user: {
        id: String(session.user.id),
        email: session.user.email || session.email || undefined,
      },
    };
  }

  // Back-compat or raw backend response: { access_token?, user_id, email }
  if (session.user_id) {
    return {
      access_token: session.access_token || null,
      user: {
        id: String(session.user_id),
        email: session.email || undefined,
      },
    };
  }

  return null;
}

function readStoredSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return normalizeSession(JSON.parse(raw));
  } catch {
    return null;
  }
}

function writeStoredSession(session) {
  if (!session) {
    localStorage.removeItem(STORAGE_KEY);
    setAccessToken(null);
    return;
  }
  const normalized = normalizeSession(session);
  if (!normalized) {
    localStorage.removeItem(STORAGE_KEY);
    setAccessToken(null);
    return;
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
  setAccessToken(normalized.access_token || null);
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => readStoredSession());
  const [isBootstrapping, setIsBootstrapping] = useState(true);

  useEffect(() => {
    const stored = readStoredSession();
    setSession(stored);
    if (stored?.access_token) setAccessToken(stored.access_token);
    setIsBootstrapping(false);
  }, []);

  const value = useMemo(() => {
    const user = session?.user || null;
    const isAuthenticated = Boolean(session?.access_token && user?.id);

    async function signup(email, password) {
      await api.post("/auth/signup", { email, password });

      // Backend signup doesn't return an access token; log in immediately.
      const loginRes = await api.post("/auth/login", { email, password });
      const data = loginRes.data;
      const next = {
        access_token: data.access_token,
        user: { id: data.user_id, email: data.email },
      };
      writeStoredSession(next);
      setSession(next);
      return next;
    }

    async function login(email, password) {
      const res = await api.post("/auth/login", { email, password });
      const data = res.data;
      const next = {
        access_token: data.access_token,
        user: { id: data.user_id, email: data.email },
      };
      writeStoredSession(next);
      setSession(next);
      return next;
    }

    function logout() {
      writeStoredSession(null);
      setSession(null);
    }

    return {
      session,
      user,
      isAuthenticated,
      isBootstrapping,
      signup,
      login,
      logout,
    };
  }, [session, isBootstrapping]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
