import { NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api/client";
import { setSessionCookies } from "../session-cookies";

type LoginResponse = {
  token: string;
  user: { email: string };
  trusted_device_token: string | null;
};

export async function POST(request: Request) {
  const { challengeId, code } = await request.json();

  if (!apiBaseUrl) {
    return NextResponse.json({ error: "API-URL ist nicht konfiguriert." }, { status: 500 });
  }

  const response = await fetch(`${apiBaseUrl}/auth/login/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ challenge_id: challengeId, code }),
  });

  if (!response.ok) {
    // Backend liefert bereits deutsche Klartext-Meldungen fuer alle
    // Fehlerfaelle dieses Endpoints (falscher Code, abgelaufen, gesperrt,
    // schon verwendet - siehe services/auth.py) - 1:1 durchreichen.
    const data = await response.json().catch(() => ({}));
    const message = typeof data.detail === "string" ? data.detail : "Code ist ungültig.";
    return NextResponse.json({ error: message }, { status: response.status });
  }

  const data = (await response.json()) as LoginResponse;
  await setSessionCookies({ token: data.token, trusted_device_token: data.trusted_device_token });

  return NextResponse.json({ user: data.user });
}
