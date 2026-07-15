"use client";

import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Modal({
  title,
  eyebrow,
  description,
  onClose,
  children,
  maxWidth = "max-w-lg",
}: {
  title: string;
  eyebrow?: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
  maxWidth?: string;
}) {
  return (
    <div className="fixed inset-0 z-[80] grid place-items-center bg-[#020711]/80 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className={`max-h-[90vh] w-full ${maxWidth} overflow-auto rounded-xl border border-white/10 bg-[#0D1B2E] p-5 shadow-2xl`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            {eyebrow && <p className="text-[10px] uppercase tracking-[.2em] text-[#69A7EA]">{eyebrow}</p>}
            <h2 className="mt-2 text-xl font-semibold text-[#F8FAFC]">{title}</h2>
            {description && <p className="mt-1 text-xs text-[#94A3B8]">{description}</p>}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}><X size={18} /></Button>
        </div>
        <div className="mt-5">{children}</div>
      </div>
    </div>
  );
}
