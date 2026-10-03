import type { Metadata } from "next";
import "./globals.css";
import { ConditionalShell } from "@/components/layout/conditional-shell";
import { brand } from "@/lib/brand";

export const metadata: Metadata = {
  title: { default: brand.appName, template: `%s | ${brand.appName}` },
  description: `Recruiting CRM for ${brand.companyName}`,
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
