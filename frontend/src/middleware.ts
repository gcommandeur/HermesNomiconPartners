import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { AUTH_COOKIE_NAME } from "@/lib/api/client";

export function middleware(request: NextRequest) {
  const hasToken = Boolean(request.cookies.get(AUTH_COOKIE_NAME)?.value);
  const { pathname } = request.nextUrl;

  if (!hasToken && pathname !== "/login") {
    const loginUrl = new URL("/login", request.url);
    // Ziel merken (z. B. die Claude-Zustimmung), damit der Login dorthin zurückführt.
    const target = `${pathname}${request.nextUrl.search}`;
    if (target !== "/") loginUrl.searchParams.set("next", target);
    return NextResponse.redirect(loginUrl);
  }
  if (hasToken && pathname === "/login") {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // api/proxy ausgeschlossen wie api/login/api/logout: ein Redirect auf
  // /login (HTML) statt der erwarteten JSON-Antwort wuerde jeden
  // client-seitigen apiGet/apiPost/... (siehe lib/api/client.ts) mit einem
  // JSON.parse-Fehler scheitern lassen statt mit einer sauberen 401.
  // icon.png/apple-icon.png (Next.js App-Icon-Konvention, siehe
  // src/app/icon.png) ausgeschlossen: ohne diese Ausnahme lieferte der
  // Browser-Favicon-Request im ausgeloggten Zustand (u.a. auf /login selbst)
  // einen 307-Redirect auf /login statt des Bildes - der Tab zeigte dann nie
  // das Icon, bevor man sich einloggt.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|icon.png|apple-icon.png|brand/|api/login|api/logout|api/proxy).*)",
  ],
};
