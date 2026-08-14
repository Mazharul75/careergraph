"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { apiFetch, restoreSession, tokens, type TokenPair } from "./api";
import type { User, UserRole } from "./types";

interface AuthState {
  user: User | null;
  /** True until the initial session restore settles. Guards against a redirect-to-login flash. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
}

export interface RegisterInput {
  email: string;
  password: string;
  full_name?: string;
  role?: UserRole;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    // The access token lives in memory, so a reload has none. Trade the stored refresh token
    // for a fresh one before deciding whether the user is signed in — otherwise every refresh
    // of the page would bounce an authenticated user to the login screen.
    let cancelled = false;
    (async () => {
      try {
        if (await restoreSession()) {
          const me = await apiFetch<User>("/api/v1/auth/me");
          if (!cancelled) setUser(me);
        }
      } catch {
        tokens.clear();
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const applyTokens = useCallback(async (pair: TokenPair) => {
    tokens.setAccess(pair.access_token);
    tokens.setRefresh(pair.refresh_token);
    setUser(await apiFetch<User>("/api/v1/auth/me"));
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const pair = await apiFetch<TokenPair>("/api/v1/auth/login", {
        method: "POST",
        body: { email, password },
        anonymous: true,
      });
      await applyTokens(pair);
      router.push("/dashboard");
    },
    [applyTokens, router],
  );

  const register = useCallback(
    async (input: RegisterInput) => {
      await apiFetch<User>("/api/v1/auth/register", {
        method: "POST",
        body: input,
        anonymous: true,
      });
      // Registration deliberately does not return tokens, so sign in as a second step.
      await login(input.email, input.password);
    },
    [login],
  );

  const logout = useCallback(async () => {
    const refresh = tokens.getRefresh();
    try {
      if (refresh) {
        await apiFetch<void>("/api/v1/auth/logout", {
          method: "POST",
          body: { refresh_token: refresh },
        });
      }
    } catch {
      // Logout is best-effort. If the network call fails the local session must still end —
      // leaving the user apparently signed in would be worse than a stale server-side token.
    } finally {
      tokens.clear();
      setUser(null);
      router.push("/login");
    }
  }, [router]);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
