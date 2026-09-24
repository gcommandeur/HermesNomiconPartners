import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { TRUSTED_DEVICE_COOKIE_NAME, apiBaseUrl } from "@/lib/api/client";
import { setSessionCookies } from "./session-cookies";

type LoginStartResponse = {
  status: "authenticated" | "challenge_required";
  challenge_id: string | null;
  expires_at: string | null;
  token: string | null;
  user: { email: string } | null;
  trusted_device_token: string | null;
};

export async function POST(request: Request) {
  const { email, password } = await request.json();

  if (!apiBaseUrl) {
    return NextResponse.json({ error: "API-URL ist nicht konfiguriert." }, { status: 500 });
  }

  const trustedDeviceToken = (await cookies()).get(TRUSTED_DEVICE_COOKIE_NAME)?.value;

  const response = await fetch(`${apiBaseUrl}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, trusted_device_token: trustedDeviceToken ?? null }),
  });

  if (!response.ok) {
    // Status-Code durchreichen (insb. 429 bei Rate-Limit) statt pauschal auf
    // 401 zu mappen - sonst ist ein Rate-Limit-Block fuer den Browser nicht
    // von einem falschen Passwort unterscheidbar (siehe login/page.tsx). Bei
    // 401 bleibt die lokalisierte Standardmeldung stehen statt des
    // Backend-Textes ("Invalid email or password", englisch, siehe
    // services/auth.py::AuthService._verify_credentials) - fuer 429 hat das
    // Backend bereits eine passende deutsche Meldung (siehe core/errors.py),
    // die 1:1 durchgereicht wird.
    const data = await response.json().catch(() => ({}));
    const message =
      response.status !== 401 && typeof data.detail === "string"
        ? data.detail
        : "E-Mail oder Passwort ist falsch.";
    return NextResponse.json({ error: message }, { status: response.status });
  }

  const data = (await response.json()) as LoginStartResponse;

  if (data.status === "authenticated") {
    // Vertrautes Geraet - 2FA wurde uebersprungen, die Session steht sofort.
    await setSessionCookies({
      token: data.token as string,
      trusted_device_token: data.trusted_device_token,
    });
    return NextResponse.json({ status: "authenticated", user: data.user });
  }

  return NextResponse.json({
    status: "challenge_required",
    challengeId: data.challenge_id,
    expiresAt: data.expires_at,
  });
}
