import { cn } from "@/lib/utils";

const tones = {
  blue: "border-brand-accent/40 bg-brand-accent-strong/45 text-brand-info",
  gray: "border-white/10 bg-white/5 text-brand-soft",
  dark: "border-[#2e3338] bg-[#1c2024] text-white",
  green: "border-brand-success/35 bg-brand-success-bg/45 text-brand-success-text",
  amber: "border-[#a7894c]/35 bg-[#5b4726]/40 text-[#e0c991]",
  red: "border-[#9b5757]/35 bg-[#5a2f35]/40 text-brand-danger-soft",
};

export function Badge({ children, tone = "gray", className, title }: {
  children: React.ReactNode;
  tone?: keyof typeof tones;
  className?: string;
  title?: string;
}) {
  return <span title={title} className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium", tones[tone], className)}>{children}</span>;
}
