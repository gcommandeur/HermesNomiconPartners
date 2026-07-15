import type { Metadata } from "next";
import "./globals.css";
import { ConditionalShell } from "@/components/layout/conditional-shell";

export const metadata: Metadata = {
  title: { default: "Hermes", template: "%s | Hermes" },
  description: "Recruiting CRM for Commandeur Consulting",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="de">
      <body>
        <ConditionalShell>{children}</ConditionalShell>
      </body>
    </html>
  );
}
