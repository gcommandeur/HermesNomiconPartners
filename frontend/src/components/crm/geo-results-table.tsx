"use client";

import { useMemo, useState } from "react";
import { MailPlus } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { StatusPill } from "@/components/crm/status-pill";
import { PaginationControls } from "@/components/crm/pagination-controls";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Input } from "@/components/ui/input";
import { apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { invalidateMailingGroupsCache } from "@/lib/api/hooks";
import { usePagination } from "@/lib/use-pagination";
import type { GeoMappingResult, MailingGroup, MailingRecipient } from "@/lib/api/types";

export function GeoResultsTable({ results }: { results: GeoMappingResult[] }) {
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [modalOpen, setModalOpen] = useState(false);
  const [groupName, setGroupName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return results;
    return results.filter((item) => {
      const haystack = [item.name, item.location, item.postal_code, item.status, ...item.tags]
        .filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(term);
    });
  }, [results, search]);

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

  return (
    <>
      <div className="mb-3 flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
        <FilterBar placeholder="Nach Standort, PLZ, Status, Rolle, Qualifikation oder Kanzlei suchen" value={search} onChange={setSearch} />
      </div>
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
