"use client";

import { useCurrentUser } from "@/lib/api/hooks";

function formatWatermarkDate(): string {
  return new Date().toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function escapeForSvg(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Ein Kachel-SVG statt hunderter einzelner DOM-Knoten - der Text (der pro
// Nutzer/Tag variiert) wird direkt ins SVG eingebettet und als
// background-image gekachelt, dadurch bleibt das Wasserzeichen bei jedem
// Scroll/Resize performant, ohne dass React bei jedem Render neue Elemente
// erzeugen/positionieren muss.
const TILE_WIDTH = 460;
const TILE_HEIGHT = 260;

// 0.01 statt der urspruenglichen 0.05: bei 0.05 war der Text auf dem
// dunklen Hintergrund (#050B14) mit blossem Auge klar lesbar (per
// Screenshot bestaetigt) - das Wasserzeichen soll aber nur ein forensischer
// Hinweis sein (bei einem geleakten Screenshot per Kontrast-/Gamma-
// Anhebung rekonstruierbar), kein im Normalbetrieb sichtbares Muster.
// Per Canvas-Pixelmessung (getImageData) auf genau diesem Hintergrund
// geprueft: 0.01 liefert noch einen klaren, von 0 verschiedenen Farbabstand
// zum Hintergrund (~3 von 255 pro Kanal) - tiefere Werte (0.008/0.006)
// rundeten im Test auf denselben Pixelwert wie 0.01 herunter, brachten also
// KEINE zusaetzliche Unsichtbarkeit, nur einen kleineren (und damit
// bruechigeren) Abstand fuer die spaetere Rekonstruktion. 0.01 ist deshalb
// der kleinste in diesem Bereich sinnvolle Wert, nicht nur ein
// Kompromisswert. Bleibt WEISS (nicht Hintergrundfarbe) - sonst waere der
// Abstand bei jeder Kontraststufe exakt 0, nicht nur mit blossem Auge
// unsichtbar.
const WATERMARK_OPACITY = 0.01;

function buildTiledWatermarkSvg(label: string): string {
  const escaped = escapeForSvg(label);
  const centerX = TILE_WIDTH / 2;
  const centerY = TILE_HEIGHT / 2;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${TILE_WIDTH}" height="${TILE_HEIGHT}">` +
    `<text x="${centerX}" y="${centerY}" transform="rotate(-30 ${centerX} ${centerY})" ` +
    `text-anchor="middle" dominant-baseline="middle" font-family="sans-serif" ` +
    `font-size="13" fill="#ffffff" fill-opacity="${WATERMARK_OPACITY}">${escaped}</text>` +
    `</svg>`
  );
}

/** Bildschirm-Wasserzeichen ueber jeder authentifizierten Seite - KEIN
 * Kopierschutz, nur ein forensischer Hinweis: bei ~1% Deckkraft (siehe
 * WATERMARK_OPACITY oben) ist der Text im normalen Betrieb fuer das blosse
 * Auge praktisch nicht wahrnehmbar, bleibt aber als winziger, aber
 * messbarer Farbunterschied zum Hintergrund erhalten und laesst sich aus
 * einem Screenshot per Kontrast-/Gamma-Anhebung (Bildbearbeitung oder ein
 * einfaches Analyse-Skript) rekonstruieren, um einen geleakten Screenshot
 * auf den verursachenden Account zurueckzufuehren (pointer-events: none,
 * sehr hoher z-index auch ueber Modals - genau das soll ja
 * mit-"fotografiert" werden).
 *
 * GRENZEN (ehrlich, kein wasserdichtes Verfahren): staerkere JPEG-
 * Kompression, eine ungewoehnliche Bildschirm-/Kamera-Farbkalibrierung oder
 * ein sehr aggressiver Weiterverarbeitungsschritt (z.B. erneutes
 * Screenshotten eines bereits komprimierten Fotos) koennen den ohnehin
 * winzigen Farbunterschied zusaetzlich abschwaechen oder ganz verschlucken -
 * das ist ein pragmatischer Kompromiss zwischen Unauffaelligkeit und
 * Rekonstruierbarkeit, keine forensisch garantierte Rueckverfolgung.
 *
 * Wird NUR in AppShell eingehaengt (siehe layout/app-shell.tsx) - die
 * Login-Seite rendert AppShell gar nicht erst (siehe
 * layout/conditional-shell.tsx), landet also automatisch nie auf /login.
 * Ohne bekannte Nutzer-E-Mail (z.B. kurzer Moment waehrend /auth/me noch
 * laedt) wird nichts gerendert statt eines Wasserzeichens ohne Zuordnung. */
export function ScreenWatermark() {
  const { data } = useCurrentUser();
  const email = data?.data.email;
  if (!email) return null;

  const label = `Commandeur Consulting · Vertraulich · ${email} · ${formatWatermarkDate()}`;
  const svg = buildTiledWatermarkSvg(label);
  const backgroundImage = `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;

  return (
    <div
      aria-hidden="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 2147483647,
        pointerEvents: "none",
        userSelect: "none",
        backgroundImage,
        backgroundRepeat: "repeat",
      }}
    />
  );
}
