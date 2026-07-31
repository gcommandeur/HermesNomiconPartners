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
// Der synchrone Sourcing-Lauf (POST /sourcing/run) macht pro PLZ einen
// externen Verzeichnis-Request mit hoeflicher Pause (~2s/Gebiet, max. 20
// Gebiete) - er braucht deshalb ein laengeres Fenster als normale
// JSON-Endpoints (siehe auch client.ts::apiPost timeoutMs).
const SOURCING_RUN_TIMEOUT_MS = 120_000;
// Anonymes-Profil-Generierung ruft synchron die Anthropic-API auf (bis zu
// 3000 Output-Tokens, siehe profile_generator.py) - das Backend selbst
// erlaubt dafuer bereits 60s (anthropic_client.py::generate_text). Mit dem
// alten 30s-Default hier lief der Proxy dem Backend regelmaessig davon und
// gab "API nicht erreichbar" zurueck, obwohl das Backend die Anfrage noch
// laenger, aber erfolgreich, verarbeitet haette - das war die tatsaechliche
// Ursache eines auf Produktion gemeldeten 500ers (der Browser gab noch
// frueher auf, siehe client.ts::apiPost timeoutMs bei diesem Aufruf).
const ANONYMOUS_PROFILE_TIMEOUT_MS = 90_000;

function timeoutForPath(joinedPath: string): number {
  if (joinedPath.endsWith("sourcing/run")) return SOURCING_RUN_TIMEOUT_MS;
  if (/\/candidates\/[^/]+\/anonymous-profile$/.test(joinedPath)) return ANONYMOUS_PROFILE_TIMEOUT_MS;
  return API_TIMEOUT_MS;
}

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

  // Der try/catch umschliesst bewusst NICHT nur den fetch()-Aufruf selbst,
  // sondern auch das Body-Einlesen (arrayBuffer()) - das AbortSignal gilt
  // fuer die gesamte fetch-Laufzeit inkl. Streaming der Antwort, ein
  // Abbruch WAEHREND des Einlesens (z.B. bei einer sehr langsamen/grossen
  // Antwort nahe am Timeout) wirft also erst hier, nicht beim fetch()-
  // Aufruf. Ohne diesen weiter gefassten try/catch entkam so ein Fehler als
  // unbehandelte Exception aus dem Next.js-Route-Handler und erschien beim
  // Nutzer als generisches "Internal Server Error" (Next.js' eigener
  // Default) statt der erwarteten sauberen JSON-Fehlermeldung - das war die
  // tatsaechliche Ursache eines auf Produktion gemeldeten 500ers.
  try {
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: body && body.byteLength > 0 ? body : undefined,
      signal: AbortSignal.timeout(timeoutForPath(path.join("/"))),
    });

    const responseHeaders = new Headers();
    const upstreamContentType = upstream.headers.get("content-type");
    if (upstreamContentType) responseHeaders.set("content-type", upstreamContentType);
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) responseHeaders.set("content-disposition", disposition);

    // Null-Body-Status-Codes (204/205/304, z.B. DELETE-Endpoints) verlangen
    // laut Fetch-Spec einen echten `null`-Body im Response-Konstruktor -
    // selbst ein leeres ArrayBuffer wirft dort "Response constructor: Cannot
    // construct a Response with a 204/205/304 status and non-null body".
    // Das landete zuvor im catch-Block darunter und meldete dem Client
    // faelschlich "API nicht erreichbar" (502), obwohl die Aktion (z.B. das
    // Loeschen) im Backend laengst erfolgreich war.
    const isNullBodyStatus = [204, 205, 304].includes(upstream.status);
    const responseBody = isNullBodyStatus ? null : await upstream.arrayBuffer();

    return new NextResponse(responseBody, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    const detail =
      error instanceof DOMException && error.name === "TimeoutError"
        ? "API antwortet nicht rechtzeitig."
        : "API nicht erreichbar";
    return NextResponse.json({ detail }, { status: 502 });
  }
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
