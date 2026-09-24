import { NextResponse } from "next/server";
import { apiBaseUrl } from "@/lib/api/client";

export async function POST(request: Request) {
  const { challengeId } = await request.json();

  if (!apiBaseUrl) {
    return NextResponse.json({ error: "API-URL ist nicht konfiguriert." }, { status: 500 });
  }

  const response = await fetch(`${apiBaseUrl}/auth/login/resend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ challenge_id: challengeId }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    // 422 bei aktivem Cooldown (siehe services/auth.py::ResendCooldownError) -
    // Backend-Text ist bereits eine deutsche Klartext-Meldung mit
    // Restwartezeit, 1:1 durchreichen.
    const message = typeof data.detail === "string" ? data.detail : "Code konnte nicht erneut verschickt werden.";
    return NextResponse.json({ error: message }, { status: response.status });
  }

  return NextResponse.json({ challengeId: data.challenge_id, expiresAt: data.expires_at });
}
