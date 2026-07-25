"use client";

import { useState } from "react";
import { Filter, Search, Sparkles } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export interface FilterOption {
  value: string;
  label: string;
}

export function FilterBar({
  placeholder = "Suchen...",
  value,
  onChange,
  statusOptions,
  statusValue,
  onStatusChange,
  onSubmit,
  aiSearch,
  ownerFilter,
  loading,
}: {
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
  statusOptions?: FilterOption[];
  statusValue?: string;
  onStatusChange?: (value: string) => void;
  /** Called when the user presses Enter in the search field. */
  onSubmit?: () => void;
  /** Optional "KI-Suche" button for natural-language queries (e.g. "aktive
   * Kandidat:innen mit Umsatzsteuer-Erfahrung im Raum Köln"). */
  aiSearch?: { loading: boolean; onClick: () => void; label?: string };
  /** Optionaler "Alle"/"Meine" Umschalter (reiner Komfort-Filter nach
   * owner_user_id, KEINE Sichtbarkeitsgrenze - jeder Nutzer sieht ohne
   * diesen Filter weiterhin alle Datensaetze). Default ist immer "Alle". */
  ownerFilter?: { mineOnly: boolean; onChange: (mineOnly: boolean) => void };
  /** Dezentes Pulsieren des Such-Icons waehrend im Hintergrund neu geladen
   * wird (z.B. debounce-getriebene Server-Suche) - bewusst KEIN Ersetzen von
   * Eingabefeld/Ergebnisliste, das wuerde den Fokus aus dem Suchfeld werfen
   * und als Flackern wahrgenommen (siehe use-server-search.ts). */
  loading?: boolean;
}) {
  const [filterOpen, setFilterOpen] = useState(false);

  return (
    <div className="mb-4 flex flex-col gap-2 sm:flex-row">
      <form
        className="relative flex-1"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit?.();
        }}
      >
        <Search
          className={`absolute left-3 top-1/2 -translate-y-1/2 text-[#959b9f] ${loading ? "animate-pulse" : ""}`}
          size={15}
        />
        <Input className="pl-9" placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
      </form>
      {aiSearch && (
        <Button variant="outline" onClick={aiSearch.onClick} disabled={aiSearch.loading || !value.trim()}>
          <Sparkles size={15} />
          {aiSearch.loading ? "Sucht…" : (aiSearch.label ?? "KI-Suche")}
        </Button>
      )}
      {ownerFilter && (
        <div className="flex overflow-hidden rounded-lg border border-white/10">
          <button
            type="button"
            className={`px-3 py-2 text-xs font-medium transition ${!ownerFilter.mineOnly ? "bg-white/10 text-white" : "text-[#94A3B8] hover:bg-white/5"}`}
            onClick={() => ownerFilter.onChange(false)}
          >
            Alle
          </button>
          <button
            type="button"
            className={`px-3 py-2 text-xs font-medium transition ${ownerFilter.mineOnly ? "bg-white/10 text-white" : "text-[#94A3B8] hover:bg-white/5"}`}
            onClick={() => ownerFilter.onChange(true)}
          >
            Meine
          </button>
        </div>
      )}
      {statusOptions && statusOptions.length > 0 && (
        <div className="relative">
          <Button variant="outline" onClick={() => setFilterOpen((open) => !open)}>
            <Filter size={15} />Filter{statusValue ? ": " + (statusOptions.find((o) => o.value === statusValue)?.label ?? "") : ""}
          </Button>
          {filterOpen && (
            <div className="absolute right-0 top-11 z-40 w-52 rounded-lg border border-white/10 bg-[#0D1B2E] p-1.5 shadow-2xl">
              <button
                className="flex w-full items-center rounded-md px-3 py-2 text-left text-xs text-[#D8DADF] hover:bg-white/8"
                onClick={() => { onStatusChange?.(""); setFilterOpen(false); }}
              >
                Alle Status
              </button>
              {statusOptions.map((option) => (
                <button
                  key={option.value}
                  className="flex w-full items-center rounded-md px-3 py-2 text-left text-xs text-[#D8DADF] hover:bg-white/8"
                  onClick={() => { onStatusChange?.(option.value); setFilterOpen(false); }}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
