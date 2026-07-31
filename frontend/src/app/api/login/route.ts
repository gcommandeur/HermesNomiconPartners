import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_COOKIE_MAX_AGE_SECONDS, AUTH_COOKIE_NAME, apiBaseUrl } from "@/lib/api/client";

export async function POST(request: Request) {
  const { email, password } = await request.json();

  if (!apiBaseUrl) {
    return NextResponse.json({ error: "API-URL ist nicht konfiguriert." }, { status: 500 });
  }

  const response = await fetch(`${apiBaseUrl}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!response.ok) {
    // Status-Code durchreichen (insb. 429 bei Rate-Limit) statt pauschal auf
    // 401 zu mappen - sonst ist ein Rate-Limit-Block fuer den Browser nicht
    // von einem falschen Passwort unterscheidbar (siehe login/page.tsx). Bei
    // 401 bleibt die lokalisierte Standardmeldung stehen statt des
    // Backend-Textes ("Invalid email or password", englisch, siehe
    // services/auth.py::AuthService.login) - fuer 429 hat das Backend bereits
    // eine passende deutsche Meldung (siehe core/errors.py), die 1:1 durchgereicht wird.
    const data = await response.json().catch(() => ({}));
    const message =
      response.status !== 401 && typeof data.detail === "string"
        ? data.detail
        : "E-Mail oder Passwort ist falsch.";
    return NextResponse.json({ error: message }, { status: response.status });
  }

  const data = (await response.json()) as { token: string; user: { email: string } };
  const cookieStore = await cookies();
  cookieStore.set(AUTH_COOKIE_NAME, data.token, {
    // httpOnly: der Token ist per document.cookie im Browser nicht mehr
    // lesbar (Schutz gegen Token-Diebstahl via XSS) - client-seitige API-
    // Aufrufe laufen dafuer ueber /api/proxy/... (siehe lib/api/client.ts::
    // apiUrl()), das den Cookie server-seitig liest. secure: Produktion
    // laeuft ausschliesslich ueber HTTPS.
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: AUTH_COOKIE_MAX_AGE_SECONDS,
  });

  return NextResponse.json({ user: data.user });
}
