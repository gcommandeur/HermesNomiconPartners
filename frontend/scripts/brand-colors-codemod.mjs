#!/usr/bin/env node
/**
 * Ersetzt feste Hex-Farben in Tailwind-Klassen durch die Design-Klassen
 * `brand-*` (Firmenschicht, siehe docs/PROJEKT_STAND.md > Zweite Firma).
 *
 *   bg-[#0D1B2E]        -> bg-brand-surface
 *   hover:text-[#94A3B8]/60 -> hover:text-brand-muted/60
 *
 * Die Zuordnung Hex -> Klasse wird AUS src/app/globals.css gelesen (Variablen
 * im :root und die @theme-inline-Zeilen). Dadurch ist sie exakt: ersetzt wird
 * nur, wenn die Variable genau diesen Hex-Wert hat. Einzige Ausnahme ist die
 * kleine Liste GRAY_MERGE (fast gleiche Grautoene werden vereinheitlicht).
 * Unbekannte Hex-Werte bleiben unveraendert und werden gemeldet.
 *
 * Aufruf (aus frontend/):
 *   node scripts/brand-colors-codemod.mjs            # Trockenlauf, nur Bericht
 *   node scripts/brand-colors-codemod.mjs --write    # Dateien aendern
 *   node scripts/brand-colors-codemod.mjs --write src/components/crm/neu.tsx
 *
 * Laeuft beliebig oft (idempotent): eine zweite Ausfuehrung aendert nichts mehr.
 */
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const css =
  readFileSync(join(root, "src/app/brand-theme.css"), "utf8") +
  readFileSync(join(root, "src/app/globals.css"), "utf8");

// Variablen: --name: #hex;  und  --color-brand-x: var(--name);
const hexByVar = new Map();
for (const m of css.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) hexByVar.set(m[1], m[2].toLowerCase());
const classByHex = new Map();
for (const m of css.matchAll(/--color-brand-([a-z0-9-]+):\s*var\(--([a-z0-9-]+)\)/g)) {
  const hex = hexByVar.get(m[2]);
  if (hex && !classByHex.has(hex)) classByHex.set(hex, m[1]);
}
// Fast gleiche Grautoene -> ein Token (Abweichung hoechstens wenige Helligkeitsstufen).
const GRAY_MERGE = {
  "#8a9095": "gray", "#858b90": "gray", "#92979c": "gray", "#8b9196": "gray",
  "#777d83": "dim", "#7b8187": "dim",
};
for (const [hex, name] of Object.entries(GRAY_MERGE)) classByHex.set(hex, name);

const UTILITIES = "bg|text|border|border-t|border-b|border-l|border-r|border-x|border-y|ring|from|to|via|divide|fill|stroke|placeholder|outline|accent|caret|decoration|shadow";
const pattern = new RegExp(`((?:[a-z0-9-]+:)*)(${UTILITIES})-\\[#([0-9a-fA-F]{6})\\](\\/\\d+)?`, "g");

function collect(paths) {
  const out = [];
  const visit = (p) => {
    const st = statSync(p);
    if (st.isDirectory()) {
      for (const name of readdirSync(p)) {
        if (name === "node_modules" || name === ".next") continue;
        visit(join(p, name));
      }
    } else if (/\.(tsx|ts|css)$/.test(p) && !/(schema\.d\.ts|openapi)/.test(p) && !p.endsWith("globals.css") && !p.endsWith("brand-theme.css")) {
      out.push(p);
    }
  };
  for (const p of paths) visit(resolve(root, p));
  return out;
}

const args = process.argv.slice(2);
const write = args.includes("--write");
const targets = args.filter((a) => !a.startsWith("--"));
const files = collect(targets.length ? targets : ["src"]);

let replaced = 0;
let touched = 0;
const unknown = new Map();
for (const file of files) {
  const before = readFileSync(file, "utf8");
  const after = before.replace(pattern, (whole, variants, utility, hex, opacity = "") => {
    const cls = classByHex.get(`#${hex.toLowerCase()}`);
    if (!cls) {
      unknown.set(`#${hex.toUpperCase()}`, (unknown.get(`#${hex.toUpperCase()}`) ?? 0) + 1);
      return whole;
    }
    replaced += 1;
    return `${variants}${utility}-brand-${cls}${opacity}`;
  });
  if (after !== before) {
    touched += 1;
    if (write) writeFileSync(file, after);
  }
}

console.log(`${write ? "Geaendert" : "Wuerde aendern"}: ${replaced} Klassen in ${touched} Dateien (${files.length} geprueft).`);
if (unknown.size) {
  console.log("Nicht zugeordnet (bleiben fest):");
  for (const [hex, n] of [...unknown].sort((a, b) => b[1] - a[1])) console.log(`  ${hex}: ${n}`);
}
// Feste Farben ausserhalb von Klassen (Stil-Objekte, SVG, Diagramme): von Hand pruefen.
let loose = 0;
for (const file of files) {
  for (const line of readFileSync(file, "utf8").split("\n")) {
    if (/#[0-9a-fA-F]{6}/.test(line) && !/-\[#[0-9a-fA-F]{6}\]/.test(line)) loose += 1;
  }
}
console.log(`Feste Farben ausserhalb von Tailwind-Klassen (von Hand): ${loose} Zeilen.`);
