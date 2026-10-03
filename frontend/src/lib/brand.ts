/**
 * Firmen-Branding an EINER Stelle. Die Standardwerte sind Commandeur Consulting;
 * fuer eine weitere Firma (eigenes Repo/eigene Installation) reichen die
 * Umgebungsvariablen unten plus eigene Bilddateien unter public/brand/.
 *
 * NEXT_PUBLIC_*-Werte werden beim Build eingebettet - nach einer Aenderung neu bauen.
 * Nicht Teil dieser Konfiguration: der Briefkopf in Profil-Dokumenten, Mails und
 * Kalender-Feed (Backend, siehe docs/PROJEKT_STAND.md > Zweite Firma).
 */
export const brand = {
  /** Name der Anwendung (Tab-Titel, Login). */
  appName: process.env.NEXT_PUBLIC_BRAND_APP_NAME || "Hermes",
  /** Firmenname (Beschreibung, Wasserzeichen, Alt-Texte). */
  companyName: process.env.NEXT_PUBLIC_BRAND_COMPANY_NAME || "Commandeur Consulting",
  /** Kleines Zeichen (Login, Seitenleiste), Datei unter public/. */
  markSrc: process.env.NEXT_PUBLIC_BRAND_MARK_SRC || "/brand/commandeur-mark.png",
  /** Wortmarke neben dem Zeichen in der Seitenleiste, Datei unter public/. */
  wordmarkSrc: process.env.NEXT_PUBLIC_BRAND_WORDMARK_SRC || "/brand/commandeur-wordmark.png",
} as const;
