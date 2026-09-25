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

function buildTiledWatermarkSvg(label: string): string {
  const escaped = escapeForSvg(label);
  const centerX = TILE_WIDTH / 2;
  const centerY = TILE_HEIGHT / 2;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${TILE_WIDTH}" height="${TILE_HEIGHT}">` +
    `<text x="${centerX}" y="${centerY}" transform="rotate(-30 ${centerX} ${centerY})" ` +
    `text-anchor="middle" dominant-baseline="middle" font-family="sans-serif" ` +
    `font-size="13" fill="#ffffff" fill-opacity="0.05">${escaped}</text>` +
    `</svg>`
  );
}

/** Sehr dezentes, gekacheltes Bildschirm-Wasserzeichen ueber jeder
 * authentifizierten Seite - macht Fotos/Screenshots des Bildschirms auf
 * den verursachenden Account rueckverfolgbar, ohne die normale Bedienung
 * zu stoeren (pointer-events: none, ~5% Deckkraft, sehr hoher z-index
 * auch ueber Modals - genau das soll ja mit-"fotografiert" werden).
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
