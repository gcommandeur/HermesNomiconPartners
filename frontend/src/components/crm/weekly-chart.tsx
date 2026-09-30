"use client";

import { useRouter } from "next/navigation";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface WeeklyChartDatum {
  name: string;
  value: number;
  href?: string;
}

export function WeeklyChart({ data }: { data: WeeklyChartDatum[] }) {
  const router = useRouter();
  return (
    <div className="h-[290px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 20, right: 10, left: -20, bottom: 5 }}>
          <CartesianGrid stroke="rgba(148,163,184,.12)" vertical={false} />
          <XAxis dataKey="name" tick={{ fill: "#94A3B8", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis allowDecimals={false} tick={{ fill: "#747C89", fontSize: 10 }} axisLine={false} tickLine={false} />
          <Tooltip cursor={{ fill: "rgba(31,95,168,.08)" }} contentStyle={{ background: "#0D1B2E", border: "1px solid rgba(148,163,184,.18)", borderRadius: 8, color: "#F8FAFC" }} />
          <Bar
            dataKey="value"
            fill="#1F5FA8"
            radius={[6, 6, 0, 0]}
            label={{ position: "top", fill: "#D8DADF", fontSize: 11 }}
            className="cursor-pointer"
            onClick={(_entry, index) => {
              const href = data[index]?.href;
              if (href) router.push(href);
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
