"use client";

import { useEffect, useMemo, useState } from "react";
import { MailPlus, MapPin, SlidersHorizontal } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { GeoMapLoader } from "@/components/crm/geo-map-loader";
import { StatusPill } from "@/components/crm/status-pill";
import { PaginationControls } from "@/components/crm/pagination-controls";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { invalidateMailingGroupsCache } from "@/lib/api/hooks";
import { geocodePlace } from "@/lib/api/queries";
import { usePagination } from "@/lib/use-pagination";
import { termsStatusLabel } from "@/lib/utils";
import type { GeoMappingResult, MailingGroup, MailingRecipient } from "@/lib/api/types";

const FEE_TIER_LABELS: Record<string, string> = {
  standard: "Standard (27 %)",
  nachlass_1: "Nachlass 1 (25 %)",
  nachlass_2: "Nachlass 2 (23 %)",
  individuell: "Individuell",
};

/** Erdradius in km fuer die Haversine-Distanz der Umkreis-Suche - bei der
 * aktuellen Datenmenge (Hunderte, keine Zehntausende Datensaetze) reicht eine
 * clientseitige Berechnung ohne eigenen Radius-Endpunkt. */
function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** Distinct, nicht-leere Werte eines Feldes als Dropdown-Optionen - baut die
 * Filter direkt aus den tatsaechlich geladenen Daten auf, statt fest codierte
 * Werte zu erfinden, die es in der Datenbank vielleicht gar nicht gibt. */
function distinctValues(results: GeoMappingResult[], pick: (item: GeoMappingResult) => string | null | undefined): string[] {
  const values = new Set<string>();
  for (const item of results) {
    const value = pick(item);
    if (value) values.add(value);
  }
  return Array.from(values).sort((a, b) => a.localeCompare(b, "de"));
}

/** Geo Mapping ist eine reine Kanzleien-Umkreissuche (Auftrag "Geo Mapping
 * auf reine Kanzleien-Suche reduzieren") - die frueher kandidatenzentrierte
 * Umkreissuche (zweite Spalte, eigene Kandidaten-Filter) uebernimmt jetzt die
 * "CV Out"-Kampagne direkt am Kandidaten. `results` enthaelt deshalb nur noch
 * Kanzleien (siehe GeoMappingResult-Typ, kein `kind`-Feld mehr). */
export function GeoResultsTable({ results }: { results: GeoMappingResult[] }) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [modalOpen, setModalOpen] = useState(false);
  const [groupName, setGroupName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const [placeQuery, setPlaceQuery] = useState("");
  const [radiusEnabled, setRadiusEnabled] = useState(false);
  const [radiusKm, setRadiusKm] = useState("25");
  // Der getippte Ort/PLZ-Wert selbst dient als Umkreis-Zentrum - wird per
  // Backend-Endpunkt (GET /geo-mapping/geocode, gleiche Stadt/PLZ-Zonen-Logik
  // wie services/geo.py::resolve_place_query) aufgeloest, debounced damit
  // nicht bei jedem Tastenanschlag ein Request rausgeht.
  const [resolvedCenter, setResolvedCenter] = useState<{ latitude: number; longitude: number } | null>(null);
  const [geocoding, setGeocoding] = useState(false);

  useEffect(() => {
    const query = placeQuery.trim();
    if (!radiusEnabled || !query) {
      setResolvedCenter(null);
      return;
    }
    let cancelled = false;
    setGeocoding(true);
    const timeout = setTimeout(async () => {
      try {
        const result = await geocodePlace(query);
        if (cancelled) return;
        setResolvedCenter(
          result.data.latitude != null && result.data.longitude != null
            ? { latitude: result.data.latitude, longitude: result.data.longitude }
            : null,
        );
      } finally {
        if (!cancelled) setGeocoding(false);
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timeout);
    };
  }, [placeQuery, radiusEnabled]);

  const [clientSearch, setClientSearch] = useState("");
  const [termsStatusFilter, setTermsStatusFilter] = useState("");
  const [feeTierFilter, setFeeTierFilter] = useState("");
  const [activeVacanciesOnly, setActiveVacanciesOnly] = useState(false);

  const termsStatusOptions = useMemo(() => distinctValues(results, (item) => item.terms_status), [results]);
  const feeTierOptions = useMemo(() => distinctValues(results, (item) => item.fee_tier), [results]);

  // Gemeinsamer Ort/PLZ- und Umkreis-Filter.
  function matchesSharedFilters(item: GeoMappingResult): boolean {
    // Bei aktiver, erfolgreich aufgeloester Umkreissuche dient placeQuery
    // NUR als Umkreis-Zentrum - der Substring-Textfilter wuerde sonst
    // zusaetzlich verlangen, dass location/postal_code exakt den getippten
    // Text enthalten (z.B. "41199"), was bei den allerwenigsten Treffern im
    // Radius zutrifft und die Umkreissuche faktisch auf ~0 Ergebnisse
    // reduziert hat, obwohl es real Hunderte Treffer im Radius gibt.
    if (radiusEnabled && resolvedCenter) {
      if (item.latitude == null || item.longitude == null) return false;
      const radius = Number(radiusKm) || 0;
      return haversineKm(resolvedCenter.latitude, resolvedCenter.longitude, item.latitude, item.longitude) <= radius;
    }

    const place = placeQuery.trim().toLowerCase();
    if (place) {
      const haystack = `${item.location} ${item.postal_code ?? ""}`.toLowerCase();
      if (!haystack.includes(place)) return false;
    }
    return true;
  }

  const clientResults = useMemo(() => {
    const term = clientSearch.trim().toLowerCase();
    return results.filter((item) => {
      if (!matchesSharedFilters(item)) return false;
      if (term) {
        const haystack = [item.name, ...item.tags].filter(Boolean).join(" ").toLowerCase();
        if (!haystack.includes(term)) return false;
      }
      if (termsStatusFilter && item.terms_status !== termsStatusFilter) return false;
      if (feeTierFilter && item.fee_tier !== feeTierFilter) return false;
      if (activeVacanciesOnly && !item.active_vacancy_count) return false;
      return true;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results, clientSearch, termsStatusFilter, feeTierFilter, activeVacanciesOnly, placeQuery, radiusEnabled, resolvedCenter, radiusKm]);

  const clientPagination = usePagination(clientResults);

  const selectedItems = useMemo(
    () => results.filter((item) => selectedIds.has(item.id)),
    [results, selectedIds],
  );

  function toggle(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleAllVisible(pageItems: GeoMappingResult[]) {
    const allSelected = pageItems.length > 0 && pageItems.every((item) => selectedIds.has(item.id));
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allSelected) pageItems.forEach((item) => next.delete(item.id));
      else pageItems.forEach((item) => next.add(item.id));
      return next;
    });
  }

  async function createGroupFromSelection() {
    if (!groupName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const recipients: MailingRecipient[] = selectedItems.map((item) => ({
        kind: "client",
        id: item.id,
        name: item.name,
        email: item.email ?? null,
      }));
      await apiPost<MailingGroup>("/mailing-groups", { name: groupName.trim(), recipients });
      void invalidateMailingGroupsCache();
      setDone(`Gruppe "${groupName.trim()}" mit ${recipients.length} Empfänger:innen angelegt.`);
      setGroupName("");
      setSelectedIds(new Set());
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Gruppe konnte nicht angelegt werden.");
    } finally {
      setBusy(false);
    }
  }

  const selectClass = "h-9 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-2.5 text-xs text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
  const labelClass = "mb-1 block text-[10px] uppercase tracking-wider text-[#94A3B8]";

  const allVisibleSelected = clientPagination.pageItems.length > 0 && clientPagination.pageItems.every((item) => selectedIds.has(item.id));

  return (
    <>
      <Card className="mb-5 min-h-[360px] overflow-hidden p-0">
        <GeoMapLoader results={clientResults} />
      </Card>

      {/* Gemeinsamer Ort/PLZ-Filter - echte Freitext-Adress-/Ortssuche, keine
       * reine Radius-Eingabe. Bewusst OHNE Autocomplete-Dropdown (die Karte
       * oben zeigt die Treffer ohnehin schon visuell). Die Umkreissuche ist
       * eine separat aktivierbare Zusatzoption ("Umkreissuche aktivieren"). */}
      <Card className="mb-3">
        <CardContent>
          <div className="mb-3 flex items-center gap-2"><MapPin size={15} className="text-[#D8DADF]" /><h2 className="text-sm font-semibold">Ort / PLZ</h2></div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="sm:col-span-2">
              <label className={labelClass}>Ort oder PLZ suchen</label>
              <Input
                placeholder="z.B. München oder 80331"
                value={placeQuery}
                onChange={(e) => setPlaceQuery(e.target.value)}
              />
            </div>
            <div className="flex items-end pb-0.5">
              <label className="flex items-center gap-2 text-xs text-[#CBD5E1]">
                <input type="checkbox" checked={radiusEnabled} onChange={(e) => setRadiusEnabled(e.target.checked)} />
                Umkreissuche aktivieren
              </label>
            </div>
            {radiusEnabled && resolvedCenter && (
              <div>
                <label className={labelClass}>Radius um &quot;{placeQuery.trim()}&quot; (km)</label>
                <Input type="number" min={1} value={radiusKm} onChange={(e) => setRadiusKm(e.target.value)} />
              </div>
            )}
            {radiusEnabled && !resolvedCenter && (
              <div className="flex items-end pb-0.5 text-xs text-[#8a9095]">
                {geocoding
                  ? "Ort wird aufgelöst…"
                  : placeQuery.trim()
                    ? "Ort/PLZ nicht erkannt - Umkreissuche inaktiv."
                    : "Bitte oben einen Ort oder eine PLZ eingeben."}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {selectedIds.size > 0 && (
        <div className="mb-3 flex items-center justify-between rounded-lg border border-[#1F5FA8]/30 bg-[#1F5FA8]/10 p-3 text-xs text-[#CBD5E1]">
          <span>{selectedIds.size} ausgewählt</span>
          <div className="flex items-center gap-2">
            <button className="text-[#94A3B8] underline hover:text-white" onClick={() => setSelectedIds(new Set())}>Auswahl aufheben</button>
            <Button size="sm" onClick={() => { setModalOpen(true); setDone(null); setError(null); }}>
              <MailPlus size={14} />Auswahl ins Mailing übernehmen
            </Button>
          </div>
        </div>
      )}

      <Card className="mb-3">
        <CardContent>
          <div className="mb-3 flex items-center gap-2"><SlidersHorizontal size={15} className="text-[#D8DADF]" /><h2 className="text-sm font-semibold">Kanzleien-Filter</h2></div>
          <div className="space-y-3">
            <FilterBar placeholder="Name oder Tag suchen" value={clientSearch} onChange={setClientSearch} />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className={labelClass}>AGB-Status</label>
                <select className={selectClass} value={termsStatusFilter} onChange={(e) => setTermsStatusFilter(e.target.value)}>
                  <option value="">Alle</option>
                  {termsStatusOptions.map((value) => <option key={value} value={value}>{termsStatusLabel(value)}</option>)}
                </select>
              </div>
              <div>
                <label className={labelClass}>Honorar-Stufe</label>
                <select className={selectClass} value={feeTierFilter} onChange={(e) => setFeeTierFilter(e.target.value)}>
                  <option value="">Alle</option>
                  {feeTierOptions.map((value) => <option key={value} value={value}>{FEE_TIER_LABELS[value] ?? value}</option>)}
                </select>
              </div>
              <div className="flex items-end pb-0.5">
                <label className="flex items-center gap-2 text-xs text-[#CBD5E1]">
                  <input type="checkbox" checked={activeVacanciesOnly} onChange={(e) => setActiveVacanciesOnly(e.target.checked)} />
                  Nur mit aktiven Vakanzen
                </label>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">Kanzleien ({clientResults.length})</h3>
      {/* Mobile (<lg): Karten statt der 7-spaltigen Tabelle, siehe
       * candidates-table.tsx fuer denselben Fix + Begruendung (Nutzer-
       * Feedback "mobile Version nicht passend") - Checkbox-Auswahl fuer
       * "ins Mailing uebernehmen" bleibt erhalten. */}
      <div className="space-y-2 lg:hidden">
        {clientPagination.pageItems.map((item) => (
          <label
            key={item.id}
            className="flex items-start gap-3 rounded-lg border border-white/10 bg-[#12243A] p-3"
          >
            <input
              type="checkbox"
              className="mt-1 shrink-0"
              checked={selectedIds.has(item.id)}
              onChange={() => toggle(item.id)}
              aria-label={`${item.name} auswählen`}
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 truncate text-sm font-semibold text-[#D8DADF]">{item.name}</p>
                <StatusPill status={item.status} />
              </div>
              <p className="mt-0.5 truncate text-xs text-[#94A3B8]">
                {item.location}{item.postal_code ? ` · ${item.postal_code}` : ""}
              </p>
              {item.tags.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {item.tags.map((tag, index) => <span key={`${item.id}-tag-${index}-${tag}`} className="rounded bg-[#102A4C]/70 px-2 py-1 text-[10px] text-[#CBD5E1]">{tag}</span>)}
                </div>
              )}
              <p className="mt-1.5 text-[11px] text-[#8a9095]">{item.mailing_ready ? "übertragbar" : "gesperrt"}</p>
            </div>
          </label>
        ))}
        {clientResults.length === 0 && (
          <p className="py-8 text-center text-xs text-[#8a9095]">Keine Ergebnisse.</p>
        )}
      </div>
      <div className="hidden lg:block">
        <DataTable headers={["", "Name", "Standort", "PLZ", "Status", "Tags", "Mailing"]}>
          {clientPagination.pageItems.map((item) => (
            <tr key={item.id} className="hover:bg-[#203A5A]/35">
              <td className="w-8 px-4 py-3.5">
                <input
                  type="checkbox"
                  checked={selectedIds.has(item.id)}
                  onChange={() => toggle(item.id)}
                  aria-label={`${item.name} auswählen`}
                />
              </td>
              <td className="px-4 py-3.5 font-semibold text-[#D8DADF]">{item.name}</td>
              <td className="px-4 py-3.5">{item.location}</td>
              <td className="px-4 py-3.5">{item.postal_code ?? "—"}</td>
              <td className="px-4 py-3.5"><StatusPill status={item.status} /></td>
              <td className="px-4 py-3.5"><div className="flex flex-wrap gap-1">{item.tags.map((tag, index) => <span key={`${item.id}-tag-${index}-${tag}`} className="rounded bg-[#102A4C]/70 px-2 py-1 text-[10px] text-[#CBD5E1]">{tag}</span>)}</div></td>
              <td className="px-4 py-3.5">{item.mailing_ready ? "übertragbar" : "gesperrt"}</td>
            </tr>
          ))}
          {clientResults.length === 0 && (
            <tr><td colSpan={7} className="px-4 py-8 text-center text-xs text-[#8a9095]">Keine Ergebnisse.</td></tr>
          )}
        </DataTable>
      </div>
      <PaginationControls page={clientPagination.page} pageCount={clientPagination.pageCount} onChange={clientPagination.setPage} />
      {clientPagination.pageItems.length > 0 && (
        <label className="mt-2 flex items-center gap-1.5 text-xs text-[#8a9095]">
          <input type="checkbox" checked={allVisibleSelected} onChange={() => toggleAllVisible(clientPagination.pageItems)} />
          Alle auf dieser Seite auswählen
        </label>
      )}

      {modalOpen && (
        <Modal title="Auswahl ins Mailing übernehmen" eyebrow={`${selectedIds.size} Empfänger:innen`} onClose={() => setModalOpen(false)}>
          <div className="space-y-4">
            {done && <div className="rounded-lg border border-[#4f8a68]/35 bg-[#244d38]/45 p-3 text-xs text-[#a9d6b8]">{done}</div>}
            <ErrorBanner message={error} />
            <div>
              <label className="mb-1 block text-xs text-[#94A3B8]">Name der neuen Gruppe</label>
              <Input placeholder="z.B. Umkreis Stuttgart Juli" value={groupName} onChange={(e) => setGroupName(e.target.value)} />
            </div>
            <p className="text-xs text-[#8b9196]">
              {selectedItems.filter((item) => item.email).length} von {selectedItems.length} ausgewählten Einträgen haben eine E-Mail-Adresse.
            </p>
            <div className="flex justify-end">
              <Button disabled={busy || !groupName.trim()} onClick={createGroupFromSelection}>
                {busy ? "Lege an…" : "Gruppe anlegen"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
