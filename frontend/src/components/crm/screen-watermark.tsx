"use client";

import { useCurrentUser } from "@/lib/api/hooks";
import { brand } from "@/lib/brand";

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

// Auf Nutzer-Vorgabe nochmals unter die vorherigen 0.01 gesenkt. Per
// Canvas-Pixelmessung (getImageData) auf dem echten Hintergrund (#050B14)
// systematisch durchgetestet:
//   0.01           -> +3 von 255 pro Kanal Farbabstand zum Hintergrund
//   0.005 bis 0.002 -> +1 von 255 pro Kanal (das absolute Minimum, das der
//                       Browser beim Rendern ueberhaupt noch als
//                       eigenstaendigen, vom Hintergrund unterscheidbaren
//                       Pixelwert rundet)
//   ab ca. 0.0015   -> +0, der gerenderte Pixel ist EXAKT identisch mit dem
//                       Hintergrund - das Wasserzeichen existiert an diesem
//                       Punkt nicht mehr, auch nicht theoretisch, keine
//                       Bildbearbeitung kann etwas aus einem identischen
//                       Pixel rekonstruieren.
// 0.005 ist damit das obere (robustere) Ende des noch ueberhaupt wirksamen
// Bereichs - liefert denselben minimalen Farbabstand wie 0.002, mit etwas
// mehr Puffer gegen Rendering-/Antialiasing-Schwankungen. Bleibt WEISS
// (nicht Hintergrundfarbe) - sonst waere der Abstand bei jeder Kontraststufe
// exakt 0, nicht nur mit blossem Auge unsichtbar.
const WATERMARK_OPACITY = 0.005;

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
 * Kopierschutz, nur ein forensischer Hinweis: bei ~0.5% Deckkraft (siehe
 * WATERMARK_OPACITY oben) ist der Text im normalen Betrieb fuer das blosse
 * Auge praktisch nicht wahrnehmbar, bleibt aber als winziger, aber
 * messbarer Farbunterschied zum Hintergrund erhalten und laesst sich aus
 * einem Screenshot per Kontrast-/Gamma-Anhebung (Bildbearbeitung oder ein
 * einfaches Analyse-Skript) rekonstruieren, um einen geleakten Screenshot
 * auf den verursachenden Account zurueckzufuehren (pointer-events: none,
 * sehr hoher z-index auch ueber Modals - genau das soll ja
 * mit-"fotografiert" werden).
 *
 * GRENZEN (ehrlich, kein wasserdichtes Verfahren): bei 0.005 betraegt der
 * Farbabstand zum Hintergrund nur noch +1 von 255 pro Kanal - das absolute
 * Minimum, das ueberhaupt noch als eigener Pixelwert gerendert wird (siehe
 * Messwerte oben). JEDE verlustbehaftete Kompression (schon normales JPEG,
 * nicht erst starke), eine abweichende Bildschirm-/Kamera-Farbkalibrierung
 * oder ein erneutes Screenshotten/Fotografieren eines bereits komprimierten
 * Bildes kann diesen einen Schritt vollstaendig verschlucken. Verlaesslich
 * rekonstruierbar ist das nur aus einem unkomprimierten/verlustfreien
 * Screenshot (PNG) mit gezielter Tonwert-/Kurven-Anhebung, nicht aus einem
 * bereits verschickten/hochgeladenen Foto. Bewusste Entscheidung fuer
 * maximale Unauffaelligkeit auf Kosten der Rekonstruierbarkeit - keine
 * forensisch garantierte Rueckverfolgung.
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

  const label = `${brand.companyName} · Vertraulich · ${email} · ${formatWatermarkDate()}`;
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
