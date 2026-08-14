/**
 * API client with transparent access-token refresh.
 *
 * The subtle part is concurrency, and it is a direct consequence of ADR-0007: refresh tokens
 * are **single-use and rotating**, and presenting a spent one is treated as theft — the backend
 * revokes the entire session family.
 *
 * So if three requests 401 at the same moment and each independently calls /auth/refresh, the
 * first succeeds and the other two present a token that was just spent. The backend correctly
 * concludes the token was stolen and logs the user out. The security control fires on our own
 * client.
 *
 * `refreshInFlight` below is the fix: the first 401 starts a refresh, every other request
 * awaits that same promise, and exactly one rotation happens. This is a single-flight guard,
 * and it is the reason the client is not just `fetch` with a header.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REFRESH_STORAGE_KEY = "careergraph.refresh_token";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * The access token is held in memory only.
 *
 * Keeping it out of localStorage means a page reload discards it and we re-derive one from the
 * refresh token. That is a deliberate trade: it narrows the window in which a stolen browser
 * profile yields a directly usable credential, at the cost of one extra request on load.
 */
let accessToken: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;

export const tokens = {
  setAccess(token: string | null) {
    accessToken = token;
  },
  getAccess(): string | null {
    return accessToken;
  },
  setRefresh(token: string | null) {
    if (typeof window === "undefined") return;
    if (token) window.localStorage.setItem(REFRESH_STORAGE_KEY, token);
    else window.localStorage.removeItem(REFRESH_STORAGE_KEY);
  },
  getRefresh(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_STORAGE_KEY);
  },
  clear() {
    accessToken = null;
    tokens.setRefresh(null);
  },
};

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    // FastAPI returns {detail: string} for our domain errors and {detail: [...]} for Pydantic
    // validation failures. Both must render as something a person can read.
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((d: { msg?: string }) => d.msg ?? "Invalid input").join(", ");
    }
  } catch {
    /* not JSON — fall through */
  }
  return response.statusText || "Request failed";
}

/** Exchange the stored refresh token for a new pair. At most one runs at a time. */
async function refreshAccessToken(): Promise<string | null> {
  const refresh = tokens.getRefresh();
  if (!refresh) return null;

  const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });

  if (!response.ok) {
    // The refresh token is spent, expired, or was revoked by reuse detection. Either way the
    // session is over — clearing prevents an endless refresh loop against a dead token.
    tokens.clear();
    return null;
  }

  const pair: TokenPair = await response.json();
  tokens.setAccess(pair.access_token);
  // Store the *new* refresh token. Forgetting this line means the next refresh presents an
  // already-spent token and trips reuse detection.
  tokens.setRefresh(pair.refresh_token);
  return pair.access_token;
}

function refreshOnce(): Promise<string | null> {
  refreshInFlight ??= refreshAccessToken().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Skip the Authorization header — used by login and register. */
  anonymous?: boolean;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, anonymous, headers, ...rest } = options;

  const send = async (token: string | null): Promise<Response> => {
    const isFormData = body instanceof FormData;
    return fetch(`${API_URL}${path}`, {
      ...rest,
      headers: {
        ...(isFormData ? {} : body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let response = await send(anonymous ? null : tokens.getAccess());

  // One retry, and only one. A second 401 after a successful refresh means the problem is not
  // an expired token, and retrying again would loop.
  if (response.status === 401 && !anonymous) {
    const token = await refreshOnce();
    if (token) response = await send(token);
  }

  if (!response.ok) throw new ApiError(response.status, await parseError(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Restore a session on page load by trading the stored refresh token for an access token. */
export async function restoreSession(): Promise<boolean> {
  if (!tokens.getRefresh()) return false;
  return (await refreshOnce()) !== null;
}
