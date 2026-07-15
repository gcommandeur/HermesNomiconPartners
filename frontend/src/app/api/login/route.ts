import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_COOKIE_NAME, apiBaseUrl } from "@/lib/api/client";

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
    return NextResponse.json({ error: "E-Mail oder Passwort ist falsch." }, { status: 401 });
  }

  const data = (await response.json()) as { token: string; user: { email: string } };
  const cookieStore = await cookies();
  cookieStore.set(AUTH_COOKIE_NAME, data.token, {
    httpOnly: false,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 14,
  });

  return NextResponse.json({ user: data.user });
}
