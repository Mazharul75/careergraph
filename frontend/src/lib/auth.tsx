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
import type { ForgotPasswordResult, RegisterResult, User, UserRole } from "./types";

interface AuthState {
  user: User | null;
  /** True until the initial session restore settles. Guards against a redirect-to-login flash. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  /** Does not sign the account in — an unverified account cannot get a session yet. The
   * caller (the register page) reads the result to show a "check your email" screen. */
  register: (input: RegisterInput) => Promise<RegisterResult>;
  logout: () => Promise<void>;
  verifyEmail: (token: string) => Promise<void>;
  resendVerification: (email: string) => Promise<void>;
  forgotPassword: (email: string) => Promise<ForgotPasswordResult>;
  resetPassword: (token: string, newPassword: string) => Promise<void>;
  googleSignIn: (idToken: string) => Promise<void>;
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

  const register = useCallback(async (input: RegisterInput): Promise<RegisterResult> => {
    // Deliberately does not sign in afterward. A freshly registered account cannot pass the
    // login gate until its email is verified, so the only honest next step is the "check
    // your email" screen the register page shows from this return value.
    return apiFetch<RegisterResult>("/api/v1/auth/register", {
      method: "POST",
      body: input,
      anonymous: true,
    });
  }, []);

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

  const verifyEmail = useCallback(async (token: string) => {
    await apiFetch<User>("/api/v1/auth/verify-email", {
      method: "POST",
      body: { token },
      anonymous: true,
    });
  }, []);

  const resendVerification = useCallback(async (email: string) => {
    // Always 204 regardless of what actually happened server-side — see the API docstring.
    await apiFetch<void>("/api/v1/auth/resend-verification", {
      method: "POST",
      body: { email },
      anonymous: true,
    });
  }, []);

  const forgotPassword = useCallback(async (email: string): Promise<ForgotPasswordResult> => {
    return apiFetch<ForgotPasswordResult>("/api/v1/auth/forgot-password", {
      method: "POST",
      body: { email },
      anonymous: true,
    });
  }, []);

  const resetPassword = useCallback(async (token: string, newPassword: string) => {
    await apiFetch<User>("/api/v1/auth/reset-password", {
      method: "POST",
      body: { token, new_password: newPassword },
      anonymous: true,
    });
    // A reset revokes every session server-side, including any this browser might still
    // hold — clearing locally keeps the two in sync rather than leaving a dead refresh
    // token sitting in storage until it fails on its own.
    tokens.clear();
  }, []);

  const googleSignIn = useCallback(
    async (idToken: string) => {
      const pair = await apiFetch<TokenPair>("/api/v1/auth/google", {
        method: "POST",
        body: { id_token: idToken },
        anonymous: true,
      });
      await applyTokens(pair);
      router.push("/dashboard");
    },
    [applyTokens, router],
  );

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      register,
      logout,
      verifyEmail,
      resendVerification,
      forgotPassword,
      resetPassword,
      googleSignIn,
    }),
    [
      user,
      loading,
      login,
      register,
      logout,
      verifyEmail,
      resendVerification,
      forgotPassword,
      resetPassword,
      googleSignIn,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
