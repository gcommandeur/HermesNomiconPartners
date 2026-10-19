// NOMICON: Kundenfreigabe von Stundenzetteln per Link - öffentlicher Zugang OHNE Login.
//
// Schmale Weiterleitung an GET /public/timesheets/{token} sowie POST .../approve und .../reject
// im Backend (siehe backend/src/cc_crm/api/v1/staffing_public.py). Bewusst NICHT der allgemeine
// /api/proxy: der hängt den Login-Cookie an und gibt die echte Client-IP nicht weiter. Hier gilt:
//  - nur diese drei Pfadformen werden durchgelassen (alles andere: 404),
//  - kein Cookie und kein Authorization-Header gehen ans Backend,
//  - die Client-IP (CF-Connecting-IP bzw. X-Forwarded-For) wird weitergereicht, damit die
//    Ratenbegrenzung des Backends pro Kunde zählt und nicht alle Kunden eine Sperre teilen.
import { NextResponse, type NextRequest } from "next/server";
import { apiBaseUrl } from "@/lib/api/client";

const PATH_PATTERN = /^[A-Za-z0-9_-]{8,200}(\/(approve|reject))?$/;
const TIMEOUT_MS = 15_000;

function json(detail: string, status: number): NextResponse {
  return NextResponse.json({ detail }, { status, headers: { "cache-control": "no-store" } });
}

async function handler(request: NextRequest, context: { params: Promise<{ path: string[] }> }): Promise<NextResponse> {
  const { path } = await context.params;
  const joined = path.join("/");
  const isDecision = joined.includes("/");
  if (!PATH_PATTERN.test(joined) || (request.method === "GET") === isDecision) {
    return json("Nicht gefunden.", 404);
  }
  if (!apiBaseUrl) return json("API-URL ist nicht konfiguriert.", 500);

  const headers = new Headers({ accept: "application/json" });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  for (const name of ["cf-connecting-ip", "x-forwarded-for"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const body = request.method === "GET" ? undefined : await request.arrayBuffer();
    const upstream = await fetch(`${apiBaseUrl}/public/timesheets/${joined}`, {
      method: request.method,
      headers,
      body: body && body.byteLength > 0 ? body : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    return new NextResponse(await upstream.arrayBuffer(), {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
        "referrer-policy": "no-referrer",
      },
    });
  } catch {
    return json("Der Dienst ist gerade nicht erreichbar. Bitte später erneut versuchen.", 502);
  }
}

export const GET = handler;
export const POST = handler;
