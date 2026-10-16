// NOMICON: Sichtbarkeitsregel des Outlook-Hinweises (reine Funktion, testbar). Der Hinweis erscheint nur
// dort, wo er hilft (Übersicht, Kalender, Mailing), nicht im Demo-Modus und nicht, solange der Nutzer
// "Später" gewählt hat (für mehrere Tage, im Browser gemerkt).
export const OUTLOOK_BANNER_PATHS = ["/", "/kalender", "/mailing"];
export const OUTLOOK_SNOOZE_DAYS = 3;
export const OUTLOOK_SNOOZE_KEY = "outlook-banner-snooze-until";

export function isOutlookBannerPath(pathname: string): boolean {
  return OUTLOOK_BANNER_PATHS.some((path) => (path === "/" ? pathname === "/" : pathname === path || pathname.startsWith(`${path}/`)));
}

/** `snoozedUntil`: Zeitpunkt in ms (Date.now()-Skala) oder null. */
export function shouldShowOutlookBanner(input: {
  state: string | null | undefined;
  pathname: string;
  snoozedUntil: number | null;
  now: number;
  demo: boolean;
}): boolean {
  if (input.demo) return false;
  if (!input.state || input.state === "connected") return false;
  if (!isOutlookBannerPath(input.pathname)) return false;
  if (input.snoozedUntil !== null && input.snoozedUntil > input.now) return false;
  return true;
}

export function snoozeUntil(now: number, days: number = OUTLOOK_SNOOZE_DAYS): number {
  return now + days * 86_400_000;
}
