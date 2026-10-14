"use client";

// NOMICON: Inhalt der Demo-Anmeldung (siehe demo-login-buttons.tsx). Wird NUR mit dem Build-Schalter
// NEXT_PUBLIC_CC_CRM_DEMO_LOGIN=true geladen und meldet nur zwei feste lokale Demo-Konten an.
import { useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";

type Persona = "admin" | "vermittler";

export default function DemoLoginInner({ onLoggedIn, onError }: { onLoggedIn: () => void | Promise<void>; onError: (message: string) => void }) {
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState<Persona | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/login/demo")
      .then((response) => response.json())
      .then((data: { enabled?: boolean }) => {
        if (!cancelled) setEnabled(data.enabled === true);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!enabled) return null;

  async function login(persona: Persona) {
    setBusy(persona);
    try {
      const response = await fetch("/api/login/demo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persona }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error ?? "Demo-Anmeldung nicht möglich.");
      await onLoggedIn();
    } catch (exception) {
      onError(exception instanceof Error ? exception.message : "Demo-Anmeldung nicht möglich.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-brand-warning/40 bg-brand-warning/10 p-3">
      <p className="flex items-center gap-2 text-xs font-medium text-brand-soft">
        <FlaskConical size={14} /> Nur lokal: Demo-Anmeldung ohne Passwort
      </p>
      <div className="flex gap-2">
        <Button type="button" variant="outline" className="flex-1" disabled={busy !== null} onClick={() => void login("admin")}>
          {busy === "admin" ? "Anmelden…" : "Demo: Admin"}
        </Button>
        <Button type="button" variant="outline" className="flex-1" disabled={busy !== null} onClick={() => void login("vermittler")}>
          {busy === "vermittler" ? "Anmelden…" : "Demo: Vermittler"}
        </Button>
      </div>
    </div>
  );
}
