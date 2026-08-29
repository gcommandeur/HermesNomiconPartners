"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { LogIn, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error ?? "Anmeldung fehlgeschlagen.");
      }
      router.replace("/");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Anmeldung fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#050B14] p-6">
      <div className="w-full max-w-sm rounded-xl border border-white/10 bg-[#0D1B2E] p-8 shadow-[0_20px_60px_rgba(0,0,0,.35)]">
        <div className="mb-6 flex flex-col items-center gap-3">
          <Image src="/brand/commandeur-mark.png" alt="Commandeur Consulting" width={64} height={64} className="h-16 w-16 object-contain" priority />
          <h1 className="text-lg font-semibold text-[#F8FAFC]">Hermes Login</h1>
          <p className="text-center text-xs text-[#94A3B8]">Internes Recruiting-CRM für Commandeur Consulting</p>
        </div>
        <form className="space-y-4" onSubmit={handleSubmit}>
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
        </form>
      </div>
    </div>
  );
}
