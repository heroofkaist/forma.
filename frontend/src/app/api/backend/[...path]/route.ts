import { NextRequest, NextResponse } from "next/server";
import { getCloudflareContext } from "@opennextjs/cloudflare";

export const dynamic = "force-dynamic";
const COOKIE = "forma_session";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  // All mutations require the browser's same-origin Origin header, including
  // login and registration, preventing both login CSRF and cookie-based CSRF.
  if (!SAFE_METHODS.has(request.method) && request.headers.get("origin") !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "Same-origin request required." }, { status: 403 });
  }
  const { path } = await context.params;
  if (path.some((part) => !part || part === "." || part === ".." || /[\\/\x00-\x1f]/.test(part)) || !["api", "academic", "assignments", "answers"].includes(path[0])) {
    return NextResponse.json({ detail: "Invalid API path." }, { status: 400 });
  }
  let workerBackend: string | undefined;
  try { workerBackend = (getCloudflareContext().env as unknown as { FORMA_BACKEND_URL?: string }).FORMA_BACKEND_URL; } catch { /* Ordinary Node deployment uses process.env. */ }
  const configured = workerBackend ?? process.env.FORMA_BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const base = new URL(configured);
  if (base.protocol !== "https:" && !(base.protocol === "http:" && ["localhost", "127.0.0.1"].includes(base.hostname))) {
    return NextResponse.json({ detail: "Backend URL must use HTTPS." }, { status: 503 });
  }
  const maxBodyBytes = 32 * 1024 * 1024;
  if (Number(request.headers.get("content-length") ?? 0) > maxBodyBytes) {
    return NextResponse.json({ detail: "Upload exceeds 32 MB request limit." }, { status: 413 });
  }
  let body: Uint8Array | undefined;
  if (!SAFE_METHODS.has(request.method) && request.body) {
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      total += chunk.value.byteLength;
      if (total > maxBodyBytes) { await reader.cancel(); return NextResponse.json({ detail: "Upload exceeds 32 MB request limit." }, { status: 413 }); }
      chunks.push(chunk.value);
    }
    body = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
  }
  const url = new URL(path.map(encodeURIComponent).join("/"), `${base.origin}/`);
  url.search = request.nextUrl.search;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const token = request.cookies.get(COOKIE)?.value;
  // Existing browser bearer sessions can finish their original lifetime during
  // migration. New credentials are exclusively persisted in HttpOnly cookies.
  const legacyAuthorization = request.headers.get("authorization");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else if (legacyAuthorization) headers.set("Authorization", legacyAuthorization);
  const logout = path.join("/") === "api/auth/logout";
  let response: Response;
  try {
    response = await fetch(logout && token?.startsWith("acct_") ? new URL("/api/accounts/logout", base.origin) : url, {
      method: request.method,
      headers,
      body: body as BodyInit | undefined,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(60_000),
    });
  } catch (error) {
    console.error("Forma backend proxy error:", {
      backendHost: base.hostname,
      error: error instanceof Error ? error.message : String(error),
    });

    return NextResponse.json(
      { detail: "Forma backend is unavailable. Please try again." },
      { status: 502 }
    );
  }
  const outputHeaders = new Headers({ "Cache-Control": "no-store" });
  for (const key of ["content-type", "content-disposition", "retry-after"]) {
    const value = response.headers.get(key);
    if (value) outputHeaders.set(key, value);
  }
  const login = path.join("/") === "api/auth/login";
  let result: NextResponse;
  if (login && response.ok) {
    const body = await response.json() as { access_token: string; expires_in: number };
    result = NextResponse.json({ authenticated: true }, { headers: outputHeaders });
    result.cookies.set(COOKIE, body.access_token, { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: body.expires_in });
  } else {
    result = new NextResponse(response.status === 204 ? null : response.body, { status: response.status, headers: outputHeaders });
  }
  if ((logout && response.ok) || response.status === 401) {
    result.cookies.set(COOKIE, "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", path: "/", maxAge: 0 });
  }
  return result;
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE, proxy as HEAD, proxy as OPTIONS };
