// NOMICON: Demo-Login ohne Passwort/2FA - nur lokal. Das Backend lehnt alles mit 404 ab, solange
// CC_CRM_DEMO_LOGIN aus ist oder die Umgebung nicht lokal/test/demo ist (siehe services/demo_login.py).
import { NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api/client";
import { setSessionCookies } from "../session-cookies";

const BUILD_ENABLED = process.env.NEXT_PUBLIC_CC_CRM_DEMO_LOGIN === "true";

export async function GET() {
  // Ohne Schalter im Build: nie nachfragen, nie "aktiv" melden.
  if (!BUILD_ENABLED || !apiBaseUrl) return NextResponse.json({ enabled: false });
  try {
    const response = await fetch(`${apiBaseUrl}/auth/demo-login/status`, { cache: "no-store" });
    const data = response.ok ? await response.json() : { enabled: false };
    return NextResponse.json({ enabled: data.enabled === true });
  } catch {
    return NextResponse.json({ enabled: false });
  }
}

export async function POST(request: Request) {
  if (!BUILD_ENABLED || !apiBaseUrl) return NextResponse.json({ error: "Nicht gefunden." }, { status: 404 });
  const { persona } = await request.json().catch(() => ({ persona: null }));
  if (persona !== "admin" && persona !== "vermittler") {
    return NextResponse.json({ error: "Unbekannte Demo-Rolle." }, { status: 400 });
  }
  const response = await fetch(`${apiBaseUrl}/auth/demo-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = typeof data.detail === "string" ? data.detail : "Demo-Anmeldung nicht möglich.";
    return NextResponse.json({ error: message }, { status: response.status });
  }
  const data = (await response.json()) as { token: string; user: { email: string } };
  await setSessionCookies({ token: data.token });
  return NextResponse.json({ status: "authenticated", user: data.user });
}
