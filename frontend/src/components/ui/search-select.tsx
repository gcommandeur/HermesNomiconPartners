"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export interface SearchSelectOption {
  value: string;
  label: string;
  sublabel?: string;
}

/** Durchsuchbares Auswahlfeld für lange Listen (z.B. 2675 Kandidaten), bei
 * denen ein normales <select> mit tausenden <option>-Zeilen unbenutzbar wird.
 * Tippen filtert clientseitig über label/sublabel, Klick außerhalb schließt. */
export function SearchSelect({
  options,
  value,
  onChange,
  placeholder = "Suchen…",
  emptyLabel = "Keine Treffer",
  clearLabel,
  required,
  className,
}: {
  options: SearchSelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  emptyLabel?: string;
  /** Label für eine explizite "nichts auswählen"-Zeile, z.B. "Noch offen" bei optionalen Feldern. */
  clearLabel?: string;
  required?: boolean;
  className?: string;
}) {
  const id = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const selected = options.find((option) => option.value === value) ?? null;

  useEffect(() => {
    if (!open) setQuery(selected ? selected.label : "");
  }, [selected, open]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term || (selected && term === selected.label.toLowerCase())) return options.slice(0, 50);
    return options
      .filter(
        (option) =>
          option.label.toLowerCase().includes(term) || option.sublabel?.toLowerCase().includes(term),
      )
      .slice(0, 50);
  }, [options, query, selected]);

  function selectOption(option: SearchSelectOption | null) {
    onChange(option?.value ?? "");
    setQuery(option?.label ?? "");
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        id={id}
        required={required && !value}
        autoComplete="off"
        className={cn(
          "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]",
          className,
        )}
        placeholder={placeholder}
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          if (value) onChange("");
        }}
      />
      {open && (
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-white/10 bg-[#0D1B2E] shadow-xl">
          {clearLabel && (
            <button
              type="button"
              className="block w-full px-3 py-2 text-left text-sm text-[#94A3B8] hover:bg-[#1F5FA8]/15"
              onClick={() => selectOption(null)}
            >
              {clearLabel}
            </button>
          )}
          {filtered.length === 0 && <p className="px-3 py-2 text-sm text-[#747C89]">{emptyLabel}</p>}
          {filtered.map((option) => (
            <button
              key={option.value}
              type="button"
              className="block w-full px-3 py-2 text-left text-sm text-[#F8FAFC] hover:bg-[#1F5FA8]/15"
              onClick={() => selectOption(option)}
            >
              {option.label}
              {option.sublabel && <span className="ml-2 text-xs text-[#747C89]">{option.sublabel}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
