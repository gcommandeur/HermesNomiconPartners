"use client";

// NOMICON: Demo-Anmeldung per Klick (ohne Passwort, ohne E-Mail-Code) - NUR lokal.
// Erscheint nur, wenn der Build NEXT_PUBLIC_CC_CRM_DEMO_LOGIN=true hat UND das Backend meldet, dass
// CC_CRM_DEMO_LOGIN in einer lokalen Umgebung aktiv ist. Ohne Schalter im Build wird die eigentliche
// Komponente (demo-login-inner.tsx) gar nicht eingebunden: ihr Code und Text kommen im Build nicht vor.
import dynamic from "next/dynamic";

type Props = { onLoggedIn: () => void | Promise<void>; onError: (message: string) => void };

const Inner =
  process.env.NEXT_PUBLIC_CC_CRM_DEMO_LOGIN === "true"
    ? dynamic<Props>(() => import("./demo-login-inner"), { ssr: false })
    : null;

export function DemoLoginButtons(props: Props) {
  return Inner ? <Inner {...props} /> : null;
}
