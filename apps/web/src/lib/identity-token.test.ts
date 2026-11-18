import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchIdentityToken, tokenCache } from "./identity-token";

const METADATA_URL =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity";

const b64url = (value: string) =>
  btoa(value).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");

const identityJwt = (ttlSeconds: number) =>
  `${b64url('{"alg":"RS256","typ":"JWT"}')}.${b64url(
    JSON.stringify({ exp: Math.floor(Date.now() / 1_000) + ttlSeconds }),
  )}.sig`;

const metadataResponse = (jwt: string) => new Response(jwt, { status: 200 });

describe("fetchIdentityToken", () => {
  beforeEach(() => {
    tokenCache.clear();
    vi.unstubAllGlobals();
  });

  it("fetches an audience-scoped ID token from the metadata server", async () => {
    const jwt = identityJwt(3600);
    const fetchMock = vi.fn(async () => metadataResponse(jwt));
    vi.stubGlobal("fetch", fetchMock);

    const token = await fetchIdentityToken("https://api.example.com");

    expect(token).toBe(jwt);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0]! as unknown as [
      string,
      { headers: Record<string, string> },
    ];
    expect(url).toBe(`${METADATA_URL}?audience=https%3A%2F%2Fapi.example.com`);
    expect(init.headers["Metadata-Flavor"]).toBe("Google");
  });

  it("caches per audience within expiry", async () => {
    const jwt = identityJwt(3600);
    const fetchMock = vi.fn(async () => metadataResponse(jwt));
    vi.stubGlobal("fetch", fetchMock);

    const first = await fetchIdentityToken("https://api.example.com");
    const token = await fetchIdentityToken("https://api.example.com");
    await fetchIdentityToken("https://other.example.com");

    expect(first).toBe(jwt);
    expect(token).toBe(jwt);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(tokenCache.get("https://api.example.com")).toStrictEqual({
      token: jwt,
      expiresAt: expect.any(Number),
    });
  });

  it("refreshes once the cached token is inside the 60s skew window", async () => {
    const jwt = identityJwt(30);
    const fetchMock = vi.fn(async () => metadataResponse(jwt));
    vi.stubGlobal("fetch", fetchMock);

    await fetchIdentityToken("https://api.example.com");
    const second = await fetchIdentityToken("https://api.example.com");

    expect(second).toBe(jwt);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("falls back to a fixed TTL when the JWT exp claim is unparsable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => metadataResponse("garbage-without-dots")));

    const token = await fetchIdentityToken("https://api.example.com");
    const entry = tokenCache.get("https://api.example.com");

    expect(token).toBe("garbage-without-dots");
    expect(entry!.expiresAt - Date.now()).toBeGreaterThan(2_900_000);
    expect(entry!.expiresAt - Date.now()).toBeLessThan(3_100_000);
  });

  it("fail-opens when the metadata server is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("unreachable");
      }),
    );
    expect(await fetchIdentityToken("https://api.example.com")).toBeNull();
  });

  it("fail-opens on non-200 metadata responses", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("forbidden", { status: 403 })));
    expect(await fetchIdentityToken("https://api.example.com")).toBeNull();
  });

  it("fail-opens when the response body is empty", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("   ", { status: 200 })));
    expect(await fetchIdentityToken("https://api.example.com")).toBeNull();
  });
});
