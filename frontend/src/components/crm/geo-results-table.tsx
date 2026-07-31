"use client";

import { useEffect, useMemo, useState } from "react";
import { MailPlus, MapPin, SlidersHorizontal } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
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

/** Ort/PLZ-Vorschlaege aus den tatsaechlich im CRM vorkommenden Standorten
 * (nicht aus einer externen Ortsliste) - Basis fuer die Autovervollstaendigung
 * der Ort/PLZ-Suche (Phase 6). Jede Vorschlagszeile traegt sowohl den
 * Ort-Text als auch die PLZ, damit die Suche danach gegen beide Felder
 * matchen kann (bidirektional: "München" findet auch nur-PLZ-Datensaetze). */
function placeSuggestions(results: GeoMappingResult[]): string[] {
  const values = new Set<string>();
  for (const item of results) {
    if (item.location && item.location !== "Ort unbekannt") values.add(item.location);
    if (item.postal_code) values.add(item.postal_code);
  }
  return Array.from(values).sort((a, b) => a.localeCompare(b, "de"));
}

export function GeoResultsTable({ results }: { results: GeoMappingResult[] }) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [modalOpen, setModalOpen] = useState(false);
  const [groupName, setGroupName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // Gemeinsame Filter, gelten fuer Kandidaten UND Kanzleien gleichzeitig
  // (Phase 6) - additiv: jede Auswahl bleibt bestehen, wenn eine andere
  // Filteroption dazukommt (keine der folgenden useState-Aenderungen setzt
  // eine andere zurueck).
  const [placeQuery, setPlaceQuery] = useState("");
  const [radiusEnabled, setRadiusEnabled] = useState(false);
  const [radiusKm, setRadiusKm] = useState("25");
  // Der getippte Ort/PLZ-Wert selbst dient als Umkreis-Zentrum (statt der
  // fruehere "bestehenden Kandidaten/Kanzlei auswaehlen"-Dropdown) - wird
  // per Backend-Endpunkt (GET /geo-mapping/geocode, gleiche Stadt/PLZ-Zonen-
  // Logik wie services/geo.py::resolve_place_query) aufgeloest, debounced
  // damit nicht bei jedem Tastenanschlag ein Request rausgeht.
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

  // Kandidaten-spezifische Filter.
  const [candidateSearch, setCandidateSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [qualificationFilter, setQualificationFilter] = useState("");
  const [noticePeriodFilter, setNoticePeriodFilter] = useState("");
  const [availableOnly, setAvailableOnly] = useState(false);

  // Kanzleien-spezifische Filter.
  const [clientSearch, setClientSearch] = useState("");
  const [termsStatusFilter, setTermsStatusFilter] = useState("");
  const [feeTierFilter, setFeeTierFilter] = useState("");
  const [activeVacanciesOnly, setActiveVacanciesOnly] = useState(false);

  const roleOptions = useMemo(() => distinctValues(results, (item) => item.role), [results]);
  const qualificationOptions = useMemo(() => distinctValues(results, (item) => item.qualification), [results]);
  const noticePeriodOptions = useMemo(() => distinctValues(results, (item) => item.notice_period), [results]);
  const termsStatusOptions = useMemo(() => distinctValues(results, (item) => item.terms_status), [results]);
  const feeTierOptions = useMemo(() => distinctValues(results, (item) => item.fee_tier), [results]);
  const placeOptions = useMemo(() => placeSuggestions(results), [results]);

  // Gemeinsamer Ort/PLZ- und Umkreis-Filter, unabhaengig von Kandidat/Kanzlei.
  function matchesSharedFilters(item: GeoMappingResult): boolean {
    const place = placeQuery.trim().toLowerCase();
    if (place) {
      const haystack = `${item.location} ${item.postal_code ?? ""}`.toLowerCase();
      if (!haystack.includes(place)) return false;
    }
    if (radiusEnabled && resolvedCenter) {
      if (item.latitude == null || item.longitude == null) return false;
      const radius = Number(radiusKm) || 0;
      if (haversineKm(resolvedCenter.latitude, resolvedCenter.longitude, item.latitude, item.longitude) > radius) return false;
    }
    return true;
  }

  const candidateResults = useMemo(() => {
    const term = candidateSearch.trim().toLowerCase();
    const todayIso = new Date().toISOString().slice(0, 10);
    return results.filter((item) => {
      if (item.kind !== "candidate") return false;
      if (!matchesSharedFilters(item)) return false;
      if (term) {
        const haystack = [item.name, item.role, item.qualification].filter(Boolean).join(" ").toLowerCase();
        if (!haystack.includes(term)) return false;
      }
      if (roleFilter && item.role !== roleFilter) return false;
      if (qualificationFilter && item.qualification !== qualificationFilter) return false;
      if (noticePeriodFilter && item.notice_period !== noticePeriodFilter) return false;
      if (availableOnly && item.available_from && item.available_from > todayIso) return false;
      return true;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results, candidateSearch, roleFilter, qualificationFilter, noticePeriodFilter, availableOnly, placeQuery, radiusEnabled, resolvedCenter, radiusKm]);

  const clientResults = useMemo(() => {
    const term = clientSearch.trim().toLowerCase();
    return results.filter((item) => {
      if (item.kind !== "client") return false;
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

  const candidatePagination = usePagination(candidateResults);
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
        kind: item.kind,
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

  function renderColumn(
    kindLabel: string,
    items: GeoMappingResult[],
    pagination: ReturnType<typeof usePagination<GeoMappingResult>>,
  ) {
    const allVisibleSelected = pagination.pageItems.length > 0 && pagination.pageItems.every((item) => selectedIds.has(item.id));
    return (
      <div className="min-w-0">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">{kindLabel} ({items.length})</h3>
        <DataTable headers={["", "Name", "Standort", "PLZ", "Status", "Tags", "Mailing"]}>
          {pagination.pageItems.map((item) => (
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
          {items.length === 0 && (
            <tr><td colSpan={7} className="px-4 py-8 text-center text-xs text-[#8a9095]">Keine Ergebnisse.</td></tr>
          )}
        </DataTable>
        <PaginationControls page={pagination.page} pageCount={pagination.pageCount} onChange={pagination.setPage} />
        {pagination.pageItems.length > 0 && (
          <label className="mt-2 flex items-center gap-1.5 text-xs text-[#8a9095]">
            <input type="checkbox" checked={allVisibleSelected} onChange={() => toggleAllVisible(pagination.pageItems)} />
            Alle auf dieser Seite auswählen
          </label>
        )}
      </div>
    );
  }

  return (
    <>
      {/* Gemeinsamer Ort/PLZ-Filter (Phase 6) - echte Adress-/Ortssuche mit
       * Autovervollstaendigung aus den tatsaechlich im CRM vorkommenden
       * Orten/PLZ (siehe placeSuggestions), keine reine Radius-Eingabe mehr.
       * Die bestehende Umkreissuche bleibt bestehen, ist aber jetzt eine
       * separat aktivierbare Zusatzoption ("Umkreissuche aktivieren"). */}
      <Card className="mb-3">
        <CardContent>
          <div className="mb-3 flex items-center gap-2"><MapPin size={15} className="text-[#D8DADF]" /><h2 className="text-sm font-semibold">Ort / PLZ</h2></div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="sm:col-span-2">
              <label className={labelClass}>Ort oder PLZ suchen</label>
              <Input
                list="geo-place-options"
                placeholder="z.B. München oder 80331"
                value={placeQuery}
                onChange={(e) => setPlaceQuery(e.target.value)}
              />
              <datalist id="geo-place-options">
                {placeOptions.map((value) => <option key={value} value={value} />)}
              </datalist>
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

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div>
          <Card className="mb-3">
            <CardContent>
              <div className="mb-3 flex items-center gap-2"><SlidersHorizontal size={15} className="text-[#D8DADF]" /><h2 className="text-sm font-semibold">Kandidaten-Filter</h2></div>
              <div className="space-y-3">
                <FilterBar placeholder="Rolle, Qualifikation oder Name suchen" value={candidateSearch} onChange={setCandidateSearch} />
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className={labelClass}>Rolle</label>
                    <select className={selectClass} value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
                      <option value="">Alle</option>
                      {roleOptions.map((value) => <option key={value} value={value}>{value}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={labelClass}>Qualifikation</label>
                    <select className={selectClass} value={qualificationFilter} onChange={(e) => setQualificationFilter(e.target.value)}>
                      <option value="">Alle</option>
                      {qualificationOptions.map((value) => <option key={value} value={value}>{value}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={labelClass}>Kündigungsfrist</label>
                    <select className={selectClass} value={noticePeriodFilter} onChange={(e) => setNoticePeriodFilter(e.target.value)}>
                      <option value="">Alle</option>
                      {noticePeriodOptions.map((value) => <option key={value} value={value}>{value}</option>)}
                    </select>
                  </div>
                  <div className="flex items-end pb-0.5">
                    <label className="flex items-center gap-2 text-xs text-[#CBD5E1]">
                      <input type="checkbox" checked={availableOnly} onChange={(e) => setAvailableOnly(e.target.checked)} />
                      Nur aktuell verfügbar
                    </label>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
          {renderColumn("Kandidaten", candidateResults, candidatePagination)}
        </div>

        <div>
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
          {renderColumn("Kanzleien", clientResults, clientPagination)}
        </div>
      </div>

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
