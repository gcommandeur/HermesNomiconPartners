import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Produziert einen minimalen, in sich geschlossenen Output-Ordner
  // (.next/standalone) - kleineres, schnelleres Docker-Image ohne node_modules.
  output: "standalone",
};

export default nextConfig;
