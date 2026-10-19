"use client";

import { usePathname } from "next/navigation";
import { AppShell } from "./app-shell";

export function ConditionalShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/login") return <>{children}</>;
  // NOMICON: Kundenfreigabe von Stundenzetteln ohne Login - keine Seitenleiste, keine Kopfzeile.
  if (pathname.startsWith("/stundenzettel/")) return <>{children}</>;
  return <AppShell>{children}</AppShell>;
}
