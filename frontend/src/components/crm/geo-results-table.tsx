"use client";

import { useMemo, useState } from "react";
import { MailPlus, SlidersHorizontal } from "lucide-react";
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

export function GeoResultsTable({ results }: { results: GeoMappingResult[] }) {
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [modalOpen, setModalOpen] = useState(false);
  const [groupName, setGroupName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // Echte Filterfelder statt der reinen Beschreibungskarte auf der Seite -
  // je ein Dropdown pro tatsaechlich im Backend vorhandenem Feld (siehe
  // GeoMappingResult in lib/api/types.ts / schemas/geo.py).
  const [roleFilter, setRoleFilter] = useState("");
  const [qualificationFilter, setQualificationFilter] = useState("");
  const [noticePeriodFilter, setNoticePeriodFilter] = useState("");
  const [availableOnly, setAvailableOnly] = useState(false);
  const [termsStatusFilter, setTermsStatusFilter] = useState("");
  const [feeTierFilter, setFeeTierFilter] = useState("");
  const [activeVacanciesOnly, setActiveVacanciesOnly] = useState(false);
  const [centerId, setCenterId] = useState("");
  const [radiusKm, setRadiusKm] = useState("25");

  const roleOptions = useMemo(() => distinctValues(results, (item) => item.role), [results]);
  const qualificationOptions = useMemo(() => distinctValues(results, (item) => item.qualification), [results]);
  const noticePeriodOptions = useMemo(() => distinctValues(results, (item) => item.notice_period), [results]);
  const termsStatusOptions = useMemo(() => distinctValues(results, (item) => item.terms_status), [results]);
  const feeTierOptions = useMemo(() => distinctValues(results, (item) => item.fee_tier), [results]);
  const geocodedResults = useMemo(() => results.filter((item) => item.latitude != null && item.longitude != null), [results]);
  const center = useMemo(() => geocodedResults.find((item) => item.id === centerId) ?? null, [geocodedResults, centerId]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    const todayIso = new Date().toISOString().slice(0, 10);
    const radius = Number(radiusKm) || 0;
    return results.filter((item) => {
      if (term) {
        const haystack = [item.name, item.location, item.postal_code, item.status, ...item.tags]
          .filter(Boolean).join(" ").toLowerCase();
        if (!haystack.includes(term)) return false;
      }
      if (roleFilter && item.role !== roleFilter) return false;
      if (qualificationFilter && item.qualification !== qualificationFilter) return false;
      if (noticePeriodFilter && item.notice_period !== noticePeriodFilter) return false;
      if (availableOnly) {
        if (item.kind !== "candidate") return false;
        if (item.available_from && item.available_from > todayIso) return false;
      }
      if (termsStatusFilter && item.terms_status !== termsStatusFilter) return false;
      if (feeTierFilter && item.fee_tier !== feeTierFilter) return false;
      if (activeVacanciesOnly) {
        if (item.kind !== "client") return false;
        if (!item.active_vacancy_count) return false;
      }
      if (center) {
        if (item.latitude == null || item.longitude == null) return false;
        if (haversineKm(center.latitude!, center.longitude!, item.latitude, item.longitude) > radius) return false;
      }
      return true;
    });
  }, [results, search, roleFilter, qualificationFilter, noticePeriodFilter, availableOnly, termsStatusFilter, feeTierFilter, activeVacanciesOnly, center, radiusKm]);

  const { pageItems, page, pageCount, setPage } = usePagination(filtered);

  const allVisibleSelected = pageItems.length > 0 && pageItems.every((item) => selectedIds.has(item.id));

  function toggle(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelectedIds((current) => {
      if (allVisibleSelected) {
        const next = new Set(current);
        pageItems.forEach((item) => next.delete(item.id));
        return next;
      }
      const next = new Set(current);
      pageItems.forEach((item) => next.add(item.id));
      return next;
    });
  }

  const selectedItems = useMemo(
    () => results.filter((item) => selectedIds.has(item.id)),
    [results, selectedIds],
  );

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

  return (
    <>
      <div className="mb-3 flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
        <FilterBar placeholder="Nach Name, Standort, PLZ oder Status suchen" value={search} onChange={setSearch} />
      </div>

      {/* Echte Filter statt der reinen Beschreibungskarte - je Feld nur
       * aufgenommen, wenn es tatsaechlich im Backend existiert (siehe
       * GeoMappingResult). Kandidaten- und Kanzlei-Filter stehen nebeneinander,
       * greifen aber nur auf ihren jeweiligen kind (siehe filtered oben). */}
      <Card className="mb-3">
        <CardContent>
          <div className="mb-3 flex items-center gap-2"><SlidersHorizontal size={15} className="text-[#D8DADF]" /><h2 className="text-sm font-semibold">Filter</h2></div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className={labelClass}>Rolle (Kandidat)</label>
              <select className={selectClass} value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
                <option value="">Alle</option>
                {roleOptions.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </div>
            <div>
              <label className={labelClass}>Qualifikation (Kandidat)</label>
              <select className={selectClass} value={qualificationFilter} onChange={(e) => setQualificationFilter(e.target.value)}>
                <option value="">Alle</option>
                {qualificationOptions.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </div>
            <div>
              <label className={labelClass}>Kündigungsfrist (Kandidat)</label>
              <select className={selectClass} value={noticePeriodFilter} onChange={(e) => setNoticePeriodFilter(e.target.value)}>
                <option value="">Alle</option>
                {noticePeriodOptions.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </div>
            <div className="flex items-end pb-0.5">
              <label className="flex items-center gap-2 text-xs text-[#CBD5E1]">
                <input type="checkbox" checked={availableOnly} onChange={(e) => setAvailableOnly(e.target.checked)} />
                Nur aktuell verfügbare Kandidat:innen
              </label>
            </div>
            <div>
              <label className={labelClass}>AGB-Status (Kanzlei)</label>
              <select className={selectClass} value={termsStatusFilter} onChange={(e) => setTermsStatusFilter(e.target.value)}>
                <option value="">Alle</option>
                {termsStatusOptions.map((value) => <option key={value} value={value}>{termsStatusLabel(value)}</option>)}
              </select>
            </div>
            <div>
              <label className={labelClass}>Honorar-Stufe (Kanzlei)</label>
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
            <div className="sm:col-span-2 lg:col-span-1">
              <label className={labelClass}>Umkreis-Zentrum</label>
              <select className={selectClass} value={centerId} onChange={(e) => setCenterId(e.target.value)}>
                <option value="">Kein Zentrum gewählt</option>
                {geocodedResults.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.location})</option>)}
              </select>
            </div>
            {center && (
              <div>
                <label className={labelClass}>Radius um Zentrum (km)</label>
                <Input type="number" min={1} value={radiusKm} onChange={(e) => setRadiusKm(e.target.value)} />
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
      <DataTable headers={["", "Typ", "Name", "Standort", "PLZ", "Status", "Tags", "Mailing"]}>
        {pageItems.map((item) => (
          <tr key={item.id} className="hover:bg-[#203A5A]/35">
            <td className="w-8 px-4 py-3.5">
              <input
                type="checkbox"
                checked={selectedIds.has(item.id)}
                onChange={() => toggle(item.id)}
                aria-label={`${item.name} auswählen`}
              />
            </td>
            <td className="px-4 py-3.5 capitalize">{item.kind}</td>
            <td className="px-4 py-3.5 font-semibold text-[#D8DADF]">{item.name}</td>
            <td className="px-4 py-3.5">{item.location}</td>
            <td className="px-4 py-3.5">{item.postal_code ?? "—"}</td>
            <td className="px-4 py-3.5"><StatusPill status={item.status} /></td>
            <td className="px-4 py-3.5"><div className="flex flex-wrap gap-1">{item.tags.map((tag, index) => <span key={`${item.id}-tag-${index}-${tag}`} className="rounded bg-[#102A4C]/70 px-2 py-1 text-[10px] text-[#CBD5E1]">{tag}</span>)}</div></td>
            <td className="px-4 py-3.5">{item.mailing_ready ? "übertragbar" : "gesperrt"}</td>
          </tr>
        ))}
      </DataTable>
      <PaginationControls page={page} pageCount={pageCount} onChange={setPage} />
      <div className="mt-3 flex items-center justify-between text-xs text-[#8a9095]">
        <span>{filtered.length} von {results.length} Ergebnissen</span>
        {pageItems.length > 0 && (
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={allVisibleSelected} onChange={toggleAllVisible} />
            Alle auf dieser Seite auswählen
          </label>
        )}
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
