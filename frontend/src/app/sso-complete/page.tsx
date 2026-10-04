"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { resetClientSession } from "@/lib/reset-client-session";

/** Landeseite nach dem Microsoft-Login: das Backend hat den Session-Cookie
 * bereits gesetzt (api/v1/microsoft_login.py). Wie beim Passwort-Login zuerst
 * alles vom vorherigen Nutzer im Browser verwerfen, dann ins CRM. */
export default function SsoCompletePage() {
  const router = useRouter();

  useEffect(() => {
    void (async () => {
      await resetClientSession();
      router.replace("/");
      router.refresh();
    })();
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#050B14] text-sm text-brand-muted">
      Anmeldung wird abgeschlossen…
    </div>
  );
}
