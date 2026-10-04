"use client";

import dynamic from "next/dynamic";
import type { GeoMappingResult } from "@/lib/api/types";

const GeoMap = dynamic(() => import("./geo-map").then((mod) => mod.GeoMap), {
  ssr: false,
  loading: () => <div className="h-[360px] w-full animate-pulse rounded-xl bg-brand-surface" />,
});

export function GeoMapLoader({ results }: { results: GeoMappingResult[] }) {
  return <GeoMap results={results} />;
}
