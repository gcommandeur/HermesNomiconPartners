import { cn } from "@/lib/utils";

const tones = {
  blue: "border-[#1F5FA8]/40 bg-[#153A66]/45 text-[#c5dcfa]",
  gray: "border-white/10 bg-white/5 text-[#CBD5E1]",
  dark: "border-[#2e3338] bg-[#1c2024] text-white",
  green: "border-[#4f8a68]/35 bg-[#244d38]/45 text-[#a9d6b8]",
  amber: "border-[#a7894c]/35 bg-[#5b4726]/40 text-[#e0c991]",
  red: "border-[#9b5757]/35 bg-[#5a2f35]/40 text-[#e4aeb4]",
};

export function Badge({ children, tone = "gray", className, title }: {
  children: React.ReactNode;
  tone?: keyof typeof tones;
  className?: string;
  title?: string;
}) {
  return <span title={title} className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium", tones[tone], className)}>{children}</span>;
}
