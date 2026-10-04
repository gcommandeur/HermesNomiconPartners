"use client";

import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Modal({
  title,
  eyebrow,
  description,
  onClose,
  children,
  maxWidth = "max-w-lg",
  variant = "center",
}: {
  title: string;
  eyebrow?: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
  maxWidth?: string;
  /** "center": heutiges Verhalten, mittige Box (Default - alle bestehenden
   * Aufrufer bleiben unveraendert). "panel": rechtsseitiges Slide-over ueber
   * volle Hoehe - fuer Inhalte, die mehr Platz brauchen (siehe
   * stage-edit-modal.tsx). */
  variant?: "center" | "panel";
}) {
  if (variant === "panel") {
    return (
      <div className="fixed inset-0 z-[80] bg-[#020711]/80 backdrop-blur-sm" onClick={onClose}>
        <div
          className="ml-auto flex h-full w-full min-w-0 max-w-full flex-col overflow-auto border-l border-white/10 bg-brand-surface p-5 shadow-2xl duration-200 sm:min-w-[480px] sm:max-w-xl lg:w-[42vw]"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="flex items-start justify-between">
            <div>
              {eyebrow && <p className="text-[10px] uppercase tracking-[.2em] text-brand-accent-light">{eyebrow}</p>}
              <h2 className="mt-2 text-xl font-semibold text-brand-text">{title}</h2>
              {description && <p className="mt-1 text-xs text-brand-muted">{description}</p>}
            </div>
            <Button variant="ghost" size="icon" onClick={onClose}><X size={18} /></Button>
          </div>
          <div className="mt-5">{children}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-[80] grid place-items-center bg-[#020711]/80 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className={cn(`max-h-[90vh] w-full ${maxWidth} overflow-auto rounded-xl border border-white/10 bg-brand-surface p-5 shadow-2xl`)}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            {eyebrow && <p className="text-[10px] uppercase tracking-[.2em] text-brand-accent-light">{eyebrow}</p>}
            <h2 className="mt-2 text-xl font-semibold text-brand-text">{title}</h2>
            {description && <p className="mt-1 text-xs text-brand-muted">{description}</p>}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}><X size={18} /></Button>
        </div>
        <div className="mt-5">{children}</div>
      </div>
    </div>
  );
}
