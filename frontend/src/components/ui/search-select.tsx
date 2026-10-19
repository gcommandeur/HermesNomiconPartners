"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useDebouncedValue } from "@/lib/use-debounced-value";

export interface SearchSelectOption {
  value: string;
  label: string;
  sublabel?: string;
}

/** Durchsuchbares Auswahlfeld für lange Listen (z.B. 2675 Kandidaten), bei
 * denen ein normales <select> mit tausenden <option>-Zeilen unbenutzbar wird.
 *
 * Zwei Modi:
 * - `options` (Standard): eine bereits geladene, kurze Liste wird clientseitig
 *   über label/sublabel gefiltert (z.B. Status-Auswahl, kleine Listen).
 * - `onSearch`: für grosse Listen (Kandidaten/Kunden) wird NICHT mehr der
 *   komplette Bestand vorgeladen - stattdessen ruft die Eingabe (entprellt um
 *   300ms) `onSearch(query)` auf und zeigt dessen Ergebnis. Vermeidet, dass
 *   allein zum Oeffnen eines Auswahlfelds Tausende Datensaetze geladen werden. */
export function SearchSelect({
  options,
  onSearch,
  value,
  onChange,
  placeholder = "Suchen…",
  emptyLabel = "Keine Treffer",
  clearLabel,
  required,
  className,
}: {
  options?: SearchSelectOption[];
  /** Server-Suche statt vorgeladener `options` - siehe Doku oben. */
  onSearch?: (query: string) => Promise<SearchSelectOption[]>;
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
  const [selectedLabel, setSelectedLabel] = useState("");
  const [asyncOptions, setAsyncOptions] = useState<SearchSelectOption[]>([]);
  const [asyncLoading, setAsyncLoading] = useState(false);
  const debouncedQuery = useDebouncedValue(query, 300);
  const requestIdRef = useRef(0);

  const selected = options?.find((option) => option.value === value) ?? null;
  const selectedDisplayLabel = onSearch ? selectedLabel : (selected?.label ?? "");

  useEffect(() => {
    if (!open) setQuery(selectedDisplayLabel);
  }, [selectedDisplayLabel, open]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!onSearch || !open) return;
    // Eine Auswahl wurde bereits getroffen und die Eingabe entspricht genau
    // deren Label (kein neuer Suchbegriff) - keinen Request ausloesen.
    if (selectedLabel && debouncedQuery === selectedLabel) return;
    const requestId = ++requestIdRef.current;
    setAsyncLoading(true);
    onSearch(debouncedQuery.trim())
      .then((results) => {
        if (requestIdRef.current === requestId) setAsyncOptions(results);
      })
      .finally(() => {
        if (requestIdRef.current === requestId) setAsyncLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onSearch, open, debouncedQuery]);

  const filtered = useMemo(() => {
    if (onSearch) return asyncOptions;
    const source = options ?? [];
    const term = query.trim().toLowerCase();
    if (!term || (selected && term === selected.label.toLowerCase())) return source.slice(0, 50);
    return source
      .filter(
        (option) =>
          option.label.toLowerCase().includes(term) || option.sublabel?.toLowerCase().includes(term),
      )
      .slice(0, 50);
  }, [onSearch, asyncOptions, options, query, selected]);

  function selectOption(option: SearchSelectOption | null) {
    onChange(option?.value ?? "");
    setQuery(option?.label ?? "");
    if (onSearch) setSelectedLabel(option?.label ?? "");
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <input
        id={id}
        required={required && !value}
        autoComplete="off"
        className={cn(
          "h-10 w-full rounded-md border border-white/10 bg-brand-surface px-3 text-sm text-brand-text outline-none focus:border-brand-accent",
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
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-md border border-white/10 bg-brand-surface shadow-xl">
          {clearLabel && (
            <button
              type="button"
              className="block w-full px-3 py-2 text-left text-sm text-brand-muted hover:bg-brand-accent/15"
              onClick={() => selectOption(null)}
            >
              {clearLabel}
            </button>
          )}
          {onSearch && asyncLoading && (
            <p className="px-3 py-2 text-sm text-brand-dim">Sucht…</p>
          )}
          {!(onSearch && asyncLoading) && filtered.length === 0 && (
            <p className="px-3 py-2 text-sm text-brand-dim">{emptyLabel}</p>
          )}
          {filtered.map((option) => (
            <button
              key={option.value}
              type="button"
              className="block w-full px-3 py-2 text-left text-sm text-brand-text hover:bg-brand-accent/15"
              onClick={() => selectOption(option)}
            >
              {option.label}
              {option.sublabel && <span className="ml-2 text-xs text-brand-dim">{option.sublabel}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
