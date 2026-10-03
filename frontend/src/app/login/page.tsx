"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { LogIn, ShieldAlert, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiBaseUrl } from "@/lib/api/client";
import { resetClientSession } from "@/lib/reset-client-session";

const RESEND_COOLDOWN_SECONDS = 60;

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Schritt 2 (Code-Eingabe) - nur befuellt, wenn das Backend "challenge_required"
  // meldet (kein vertrautes Geraet, siehe /api/login/route.ts).
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const codeInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => setResendCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  useEffect(() => {
    if (challengeId) codeInputRef.current?.focus();
  }, [challengeId]);

  // Fehlermeldung vom Microsoft-Login (Backend leitet mit ?error=... hierher
  // zurueck, siehe api/v1/microsoft_login.py). window.location statt
  // useSearchParams, damit das statische Prerendering der Seite nicht bricht.
  useEffect(() => {
    const message = new URLSearchParams(window.location.search).get("error");
    if (message) setError(message);
  }, []);

  async function handlePasswordSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error ?? "Anmeldung fehlgeschlagen.");
      }
      if (data.status === "authenticated") {
        // Vertrautes Geraet - 2FA-Schritt entfaellt komplett.
        await resetClientSession();
        router.replace("/");
        router.refresh();
        return;
      }
      setChallengeId(data.challengeId as string);
      setResendCooldown(RESEND_COOLDOWN_SECONDS);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Anmeldung fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  }

  async function handleCodeSubmit(event: React.FormEvent) {
    event.preventDefault();
    setVerifying(true);
    setError(null);
    try {
      const response = await fetch("/api/login/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challengeId, code }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error ?? "Code ist ungültig.");
      }
      await resetClientSession();
      router.replace("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Code ist ungültig.");
    } finally {
      setVerifying(false);
    }
  }

  async function handleResend() {
    setResending(true);
    setError(null);
    try {
      const response = await fetch("/api/login/resend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challengeId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error ?? "Code konnte nicht erneut verschickt werden.");
      }
      setCode("");
      setResendCooldown(RESEND_COOLDOWN_SECONDS);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Code konnte nicht erneut verschickt werden.");
    } finally {
      setResending(false);
    }
  }

  function handleBackToPassword() {
    setChallengeId(null);
    setCode("");
    setError(null);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#050B14] p-6">
      <div className="w-full max-w-sm rounded-xl border border-white/10 bg-[#0D1B2E] p-8 shadow-[0_20px_60px_rgba(0,0,0,.35)]">
        <div className="mb-6 flex flex-col items-center gap-3">
          <Image src="/brand/commandeur-mark.png" alt="Commandeur Consulting" width={64} height={64} className="h-16 w-16 object-contain" priority />
          <h1 className="text-lg font-semibold text-[#F8FAFC]">Hermes Login</h1>
        </div>

        {!challengeId ? (
          <form className="space-y-4" onSubmit={handlePasswordSubmit}>
            <div>
              <label className="mb-1 block text-xs text-[#94A3B8]" htmlFor="email">E-Mail</label>
              <input
                id="email"
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full rounded-md border border-white/10 bg-[#071426] px-3 py-2 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[#94A3B8]" htmlFor="password">Passwort</label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-md border border-white/10 bg-[#071426] px-3 py-2 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]"
              />
            </div>
            {error && (
              <div className="flex items-center gap-2 rounded-lg border border-red-400/25 bg-red-950/30 p-3 text-xs text-red-200">
                <ShieldAlert size={14} />
                {error}
              </div>
            )}
            <Button type="submit" disabled={loading} className="w-full">
              <LogIn size={15} />
              {loading ? "Anmelden…" : "Anmelden"}
            </Button>
            <div className="flex items-center gap-3 text-xs text-[#64748B]">
              <span className="h-px flex-1 bg-white/10" />
              oder
              <span className="h-px flex-1 bg-white/10" />
            </div>
            {/* Volle Seitennavigation (kein fetch): der Flow besteht aus
                Redirects ueber Microsoft und zurueck, siehe api/v1/microsoft_login.py. */}
            <a
              href={`${apiBaseUrl ?? "/api/v1"}/auth/microsoft/login`}
              className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-white/15 bg-white/5 text-sm font-medium text-[#D8DADF] transition-colors hover:bg-white/10"
            >
              Mit Microsoft anmelden
            </a>
          </form>
        ) : (
          <form className="space-y-4" onSubmit={handleCodeSubmit}>
            <div className="flex items-center gap-2 rounded-lg border border-[#1F5FA8]/30 bg-[#102A4C]/50 p-3 text-xs text-[#69A7EA]">
              <ShieldCheck size={14} />
              Wir haben einen 6-stelligen Code an {email} geschickt. Der Code ist 15 Minuten gültig.
            </div>
            <div>
              <label className="mb-1 block text-xs text-[#94A3B8]" htmlFor="code">Anmeldecode</label>
              <input
                id="code"
                ref={codeInputRef}
                type="text"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                required
                autoComplete="one-time-code"
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                className="w-full rounded-md border border-white/10 bg-[#071426] px-3 py-2 text-center text-lg tracking-[0.5em] text-[#F8FAFC] outline-none focus:border-[#1F5FA8]"
              />
            </div>
            {error && (
              <div className="flex items-center gap-2 rounded-lg border border-red-400/25 bg-red-950/30 p-3 text-xs text-red-200">
                <ShieldAlert size={14} />
                {error}
              </div>
            )}
            <Button type="submit" disabled={verifying || code.length !== 6} className="w-full">
              <LogIn size={15} />
              {verifying ? "Prüfe…" : "Code bestätigen"}
            </Button>
            <div className="flex items-center justify-between text-xs">
              <button
                type="button"
                onClick={handleBackToPassword}
                className="text-[#94A3B8] hover:text-[#F8FAFC]"
              >
                Zurück
              </button>
              <button
                type="button"
                onClick={handleResend}
                disabled={resending || resendCooldown > 0}
                className="text-[#69A7EA] hover:text-[#8FC1F2] disabled:cursor-not-allowed disabled:text-[#4A5568]"
              >
                {resendCooldown > 0
                  ? `Neuen Code anfordern (${resendCooldown}s)`
                  : resending
                    ? "Wird verschickt…"
                    : "Neuen Code anfordern"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
