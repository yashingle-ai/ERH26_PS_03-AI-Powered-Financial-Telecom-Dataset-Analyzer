const TOKEN_KEY = "erakshak.access_token";
const USER_KEY = "erakshak.username";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUsername(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(USER_KEY);
}

export function setSession(token: string, username: string) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, username);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getToken());
}

/**
 * Seconds until the current token expires; null if there is no token or its
 * `exp` cannot be read.
 *
 * The payload is only *read*, never trusted for authorisation — the server
 * verifies the signature on every request. This exists so the UI can renew
 * before a long call rather than discovering expiry as a mid-run 401.
 */
export function secondsUntilExpiry(token: string | null = getToken()): number | null {
  if (!token) return null;
  const payload = token.split(".")[1];
  if (!payload) return null;
  try {
    // base64url -> base64; atob rejects the URL-safe alphabet.
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = (JSON.parse(json) as { exp?: number }).exp;
    if (typeof exp !== "number") return null;
    return exp - Math.floor(Date.now() / 1000);
  } catch {
    return null;
  }
}

export function isExpired(token: string | null = getToken()): boolean {
  const left = secondsUntilExpiry(token);
  return left !== null && left <= 0;
}
