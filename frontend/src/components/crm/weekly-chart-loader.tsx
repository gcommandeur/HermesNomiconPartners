"use client";

import dynamic from "next/dynamic";

// recharts ist die groesste Einzelabhaengigkeit im Client-Bundle und wurde
// bisher statisch importiert, obwohl sie nur auf der Dashboard-Seite
// gebraucht wird - First Load JS dort war dadurch mit Abstand am hoechsten
// (204 kB vs. 107-132 kB auf praktisch allen anderen Seiten). Per next/dynamic
// ausgelagert, laedt es erst nach dem initialen Paint statt den First Load
// jeder Navigation zu "/" zu blockieren.
const WeeklyChart = dynamic(
  () => import("./weekly-chart").then((mod) => mod.WeeklyChart),
  {
    ssr: false,
    loading: () => <div className="h-[290px] w-full animate-pulse rounded-lg bg-[#0D1B2E]" />,
  },
);

export function WeeklyChartLoader({ data }: { data: { name: string; value: number; href?: string }[] }) {
  return <WeeklyChart data={data} />;
}
