import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { fetchIdentityToken } from "./lib/identity-token";

export async function middleware(request: NextRequest) {
  const audience = process.env.API_AUDIENCE;
  if (typeof audience !== "string" || !audience.startsWith("https://")) {
    return NextResponse.next();
  }
  const token = await fetchIdentityToken(audience);
  if (token === null) {
    return NextResponse.next();
  }
  const headers = new Headers(request.headers);
  headers.set("authorization", `Bearer ${token}`);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: ["/api/:path*"],
};
