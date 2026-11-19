const METADATA_IDENTITY_URL =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity";

const DEFAULT_TTL_MS = 3_000_000;
const SKEW_MS = 60_000;
const TIMEOUT_MS = 1_500;

export const tokenCache = new Map<string, { token: string; expiresAt: number }>();

export async function fetchIdentityToken(audience: string): Promise<string | null> {
  const now = Date.now();
  const hit = tokenCache.get(audience);
  if (hit && hit.expiresAt - SKEW_MS > now) {
    return hit.token;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const url = `${METADATA_IDENTITY_URL}?audience=${encodeURIComponent(audience)}`;
    const res = await fetch(url, {
      headers: { "Metadata-Flavor": "Google" },
      signal: controller.signal,
    });
    if (!res.ok) {
      return null;
    }
    const token = (await res.text()).trim();
    if (token === "") {
      return null;
    }
    const entry = { token, expiresAt: now + _ttlMsFromJwt(token, now) };
    tokenCache.set(audience, entry);
    return entry.token;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function _ttlMsFromJwt(token: string, now: number): number {
  const payload = token.split(".")[1];
  if (payload === undefined) {
    return DEFAULT_TTL_MS;
  }
  try {
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const claims = JSON.parse(atob(`${base64}${"=".repeat((4 - (base64.length % 4)) % 4)}`)) as {
      exp?: unknown;
    };
    const exp = typeof claims.exp === "number" ? claims.exp : Number(claims.exp ?? NaN);
    return Number.isFinite(exp) ? Math.max(exp * 1_000 - now, 0) : DEFAULT_TTL_MS;
  } catch {
    return DEFAULT_TTL_MS;
  }
}
