"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Aufklappbare Card fuer Einstellungs-/Konfigurationsseiten (Auftrag
 * "Einstellungen-Seite wirkt gequetscht") - ersetzt mehrere permanent
 * ausgeklappte Cards direkt untereinander durch klickbare Panels. Generisch
 * gehalten (title/description/icon/defaultOpen), damit spaetere
 * Einstellungs-Abschnitte dieselbe Komponente wiederverwenden koennen statt
 * das Akkordeon-Markup erneut zu duplizieren. */
export function CollapsibleSection({
  title,
  description,
  icon,
  defaultOpen = true,
  children,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex w-full items-start justify-between gap-4 p-5 text-left"
      >
        <div className="flex items-start gap-2.5">
          {icon}
          <div>
            <h2 className="font-semibold">{title}</h2>
            {description && <p className="mt-1 text-xs text-[#94A3B8]">{description}</p>}
          </div>
        </div>
        <ChevronDown
          size={18}
          className={cn(
            "mt-0.5 shrink-0 text-[#94A3B8] transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>
      {open && <CardContent className="pt-0">{children}</CardContent>}
    </Card>
  );
}
