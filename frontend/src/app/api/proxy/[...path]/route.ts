import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import { AUTH_COOKIE_NAME, apiBaseUrl } from "@/lib/api/client";

/** Same-origin Proxy zwischen Browser und dem separaten FastAPI-Backend.
 *
 * Der Login-Cookie (cc_crm_token) ist httpOnly - per JavaScript (document.
 * cookie) im Browser also nicht mehr lesbar (Schutz gegen Token-Diebstahl
 * via XSS). Bisher lasen alle client-seitigen apiGet/apiPost/.../-Aufrufe
 * (siehe lib/api/client.ts) den Token per document.cookie und schickten ihn
 * als Authorization-Header direkt ans Backend - das geht mit einem
 * httpOnly-Cookie nicht mehr.
 *
 * Stattdessen rufen Browser-seitige Aufrufe jetzt diese Route auf (siehe
 * client.ts::apiUrl()): sie laeuft server-seitig in Next.js, kann den
 * httpOnly-Cookie per next/headers lesen (das Verbot gilt nur fuer
 * document.cookie im Browser, nicht fuer den Server-Zugriff), haengt den
 * Authorization-Header an und reicht den Request unveraendert ans FastAPI-
 * Backend weiter. Der Token verlaesst dadurch nie den Server-Kontext.
 *
 * Request-/Response-Body werden bewusst als rohe Bytes (arrayBuffer) statt
 * geparst durchgereicht - so funktionieren JSON-Bodies genauso wie
 * multipart/form-data-Uploads (Content-Type inkl. Boundary wird 1:1
 * uebernommen) und binaere Downloads (Dokument-Vorschau/-Download).
 */

const API_TIMEOUT_MS = 30_000;

async function proxy(request: NextRequest, path: string[]): Promise<NextResponse> {
  if (!apiBaseUrl) {
    return NextResponse.json({ detail: "API-URL ist nicht konfiguriert." }, { status: 500 });
  }

  const token = (await cookies()).get(AUTH_COOKIE_NAME)?.value;
  const targetUrl = `${apiBaseUrl}/${path.join("/")}${request.nextUrl.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  headers.set("accept", request.headers.get("accept") ?? "application/json");
  if (token) headers.set("authorization", `Bearer ${token}`);

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const body = hasBody ? await request.arrayBuffer() : undefined;

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: body && body.byteLength > 0 ? body : undefined,
      signal: AbortSignal.timeout(API_TIMEOUT_MS),
    });
  } catch {
    return NextResponse.json({ detail: "API nicht erreichbar" }, { status: 502 });
  }

  const responseBody = await upstream.arrayBuffer();
  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType) responseHeaders.set("content-type", upstreamContentType);
  const disposition = upstream.headers.get("content-disposition");
  if (disposition) responseHeaders.set("content-disposition", disposition);

  return new NextResponse(responseBody, { status: upstream.status, headers: responseHeaders });
}

async function handler(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return proxy(request, path);
}

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const PUT = handler;
export const DELETE = handler;
