import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn("h-10 w-full rounded-md border bg-brand-surface px-3 text-sm text-brand-text outline-none placeholder:text-brand-dim focus:border-brand-accent focus:ring-2 focus:ring-brand-accent/20", className)}
      {...props}
    />
  );
}
