/** Ziel nach dem Login: wer eine geschützte Seite öffnet (z. B. die Claude-Zustimmung),
 * soll nach der Anmeldung dort landen statt auf der Startseite. Das Ziel reist als
 * `?next=` zur Login-Seite, wird in sessionStorage gemerkt (übersteht den Umweg über
 * Microsoft und die 2FA-Eingabe) und nur akzeptiert, wenn es ein relativer Pfad der
 * eigenen App ist (kein Open Redirect). */
const KEY = "hermes-post-login-target";

export function safeNextPath(raw: string | null | undefined): string | null {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return null;
  if (raw === "/login" || raw.startsWith("/login?") || raw.startsWith("/api/")) return null;
  return raw;
}

export function rememberPostLoginTarget(raw: string | null): void {
  const target = safeNextPath(raw);
  if (!target) return;
  try {
    window.sessionStorage.setItem(KEY, target);
  } catch {
    // Storage nicht verfügbar - dann eben Startseite.
  }
}

export function takePostLoginTarget(): string {
  try {
    const target = safeNextPath(window.sessionStorage.getItem(KEY));
    window.sessionStorage.removeItem(KEY);
    return target ?? "/";
  } catch {
    return "/";
  }
}
