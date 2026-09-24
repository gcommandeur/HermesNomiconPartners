import { cookies } from "next/headers";
import {
  AUTH_COOKIE_MAX_AGE_SECONDS,
  AUTH_COOKIE_NAME,
  TRUSTED_DEVICE_COOKIE_MAX_AGE_SECONDS,
  TRUSTED_DEVICE_COOKIE_NAME,
} from "@/lib/api/client";

/** Gemeinsam von /api/login/route.ts (vertrautes Geraet - 2FA uebersprungen)
 * und /api/login/verify/route.ts (Code erfolgreich geprueft) genutzt - beide
 * Pfade enden mit einer fertigen Session, siehe schemas/auth.py::
 * LoginResponse/LoginStartResponse (trusted_device_token ist in beiden
 * optional gefuellt). */
export async function setSessionCookies(data: {
  token: string;
  trusted_device_token?: string | null;
}) {
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
  if (data.trusted_device_token) {
    cookieStore.set(TRUSTED_DEVICE_COOKIE_NAME, data.trusted_device_token, {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: TRUSTED_DEVICE_COOKIE_MAX_AGE_SECONDS,
    });
  }
}
