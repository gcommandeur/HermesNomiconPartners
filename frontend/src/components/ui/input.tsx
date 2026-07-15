import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn("h-10 w-full rounded-md border bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none placeholder:text-[#747C89] focus:border-[#1F5FA8] focus:ring-2 focus:ring-[#1F5FA8]/20", className)}
      {...props}
    />
  );
}
