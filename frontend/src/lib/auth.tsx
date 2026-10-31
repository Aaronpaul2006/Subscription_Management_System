import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, get, post } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  signup: (data: { name: string; email: string; password: string; company?: string }) => Promise<User>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const queryClient = useQueryClient();

  const refresh = useCallback(async () => {
    try {
      setUser(await get<User>("auth/me/"));
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      refresh,
      login: async (email, password) => {
        const u = await post<User>("auth/login/", { email, password });
        queryClient.clear();
        setUser(u);
        return u;
      },
      signup: async (data) => {
        const u = await post<User>("auth/signup/", data);
        queryClient.clear();
        setUser(u);
        return u;
      },
      logout: async () => {
        await post("auth/logout/");
        queryClient.clear();
        setUser(null);
      },
    }),
    [user, loading, refresh, queryClient],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

export function useRole() {
  const { user } = useAuth();
  return {
    isAdmin: user?.role === "ADMIN",
    isInternal: user?.role === "ADMIN" || user?.role === "STAFF",
    isCustomer: user?.role === "CUSTOMER",
  };
}
