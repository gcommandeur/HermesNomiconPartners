/**
 * Firmen-Branding an EINER Stelle. Die Standardwerte sind Nomicon Partners (Hermes hat eigene);
 * fuer eine weitere Firma (eigenes Repo/eigene Installation) reichen die
 * Umgebungsvariablen unten plus eigene Bilddateien unter public/brand/.
 *
 * NEXT_PUBLIC_*-Werte werden beim Build eingebettet - nach einer Aenderung neu bauen.
 * Nicht Teil dieser Konfiguration: der Briefkopf in Profil-Dokumenten, Mails und
 * Kalender-Feed (Backend, siehe docs/PROJEKT_STAND.md > Zweite Firma).
 */
export const brand = {
  /** Name der Anwendung (Tab-Titel, Login). */
  appName: process.env.NEXT_PUBLIC_BRAND_APP_NAME || "Nomicon", // NOMICON
  /** Firmenname (Beschreibung, Wasserzeichen, Alt-Texte). */
  companyName: process.env.NEXT_PUBLIC_BRAND_COMPANY_NAME || "Nomicon Partners", // NOMICON
  /** Kleines Zeichen (Login, Seitenleiste), Datei unter public/. */
  markSrc: process.env.NEXT_PUBLIC_BRAND_MARK_SRC || "/brand/nomicon-mark-light.png", // NOMICON
  /** Wortmarke neben dem Zeichen in der Seitenleiste, Datei unter public/. */
  wordmarkSrc: process.env.NEXT_PUBLIC_BRAND_WORDMARK_SRC || "/brand/nomicon-wordmark-light.png", // NOMICON
} as const;
