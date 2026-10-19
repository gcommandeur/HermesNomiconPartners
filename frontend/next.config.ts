import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Produziert einen minimalen, in sich geschlossenen Output-Ordner
  // (.next/standalone) - kleineres, schnelleres Docker-Image ohne node_modules.
  output: "standalone",
  // NOMICON: Demo-Login-Schalter als feste Zeichenkette "true"/"false" in den Build einsetzen, damit
  // der Code der Demo-Anmeldung (components/crm/demo-login-inner.tsx) ohne Schalter gar nicht mitgebaut wird.
  env: {
    NEXT_PUBLIC_CC_CRM_DEMO_LOGIN: process.env.NEXT_PUBLIC_CC_CRM_DEMO_LOGIN === "true" ? "true" : "false",
  },

  // NOMICON: Umbenennung Kanzleien -> Kunden: alte Lesezeichen weiterleiten.
  async redirects() {
    return [
      { source: "/kanzleien", destination: "/kunden", permanent: true },
      { source: "/kanzleien/:path*", destination: "/kunden/:path*", permanent: true },
    ];
  },

  async headers() {
    return [
      {
        // Seiten-Routen duerfen NIE im geteilten Edge-Cache landen.
        //
        // Hintergrund (live reproduziert): /login ist statisch vorgerendert
        // und wurde deshalb mit "Cache-Control: s-maxage=31536000" (ein
        // Jahr!) ausgeliefert. Vor DO App Platform sitzt Cloudflare, das
        // sich daran haelt - und das den von Next.js korrekt gesetzten
        // "Vary: rsc, next-router-state-tree, ..."-Header beim Cache-Key
        // IGNORIERT (Cloudflare beruecksichtigt nur Accept-Encoding).
        // Dadurch teilen sich die HTML- und die RSC-Variante derselben URL
        // einen Cache-Eintrag: an einem PoP, an dem zuerst ein
        // RSC-/Prefetch-Request ankam, bekam anschliessend JEDER normale
        // Browser-Request den rohen RSC-Payload ("$Sreact.fragment ...")
        // statt der Seite. Ueber ein anderes Netz (anderer PoP) war
        // dieselbe URL unauffaellig - daher wirkte der Fehler
        // client-spezifisch.
        //
        // Ein zusaetzlicher Vary-Header wuerde nicht helfen (Cloudflare
        // wertet ihn nicht aus) - die Antwort darf schlicht nicht
        // shared-cachebar sein. Dieselben Seiten verhalten sich damit wie
        // die bereits unauffaelligen: Cache-Control "private" -> BYPASS.
        //
        // Ausschlussmuster bewusst identisch zum Middleware-Matcher
        // (src/middleware.ts): /_next/static & Co. sind unveraenderliche,
        // gehashte Assets und MUESSEN langlebig gecacht bleiben - ohne den
        // Ausschluss waere jeder Seitenaufruf unnoetig langsam.
        source: "/((?!_next/static|_next/image|favicon.ico|icon.png|apple-icon.png|brand/).*)",
        headers: [{ key: "Cache-Control", value: "private, no-store" }],
      },
    ];
  },
};

export default nextConfig;
