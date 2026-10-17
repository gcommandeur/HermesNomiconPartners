"use client";

// NOMICON: Überlassung - Einsätze (Liste mit Filtern).
import { useMemo, useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useStaffingAssignments } from "@/lib/api/staffing-hooks";
import { ASSIGNMENT_STATUS_LABELS, type StaffingAssignmentStatus } from "@/lib/api/staffing";
import { formatDate } from "@/lib/utils";
import { AssignmentStatusBadge, EmptyHint, LoadError, LoadingRows, selectClass } from "./staffing-ui";

export function StaffingAssignmentsView({ workerId, initialOverdue = false }: { workerId?: string; initialOverdue?: boolean }) {
  const [status, setStatus] = useState<StaffingAssignmentStatus | "">("");
  const [overdueOnly, setOverdueOnly] = useState(initialOverdue);
  const [search, setSearch] = useState("");
  const { data, error, isLoading, mutate } = useStaffingAssignments({ status: status || undefined, workerId, overdue: overdueOnly });
  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    const all = data?.data ?? [];
    if (!term) return all;
    return all.filter((a) => `${a.worker_name} ${a.client_name} ${a.activity ?? ""} ${a.location ?? ""}`.toLowerCase().includes(term));
  }, [data, search]);

  return (
    <div>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <Input aria-label="Einsätze durchsuchen" placeholder="Suchen: Name, Kunde, Ort…" value={search} onChange={(e) => setSearch(e.target.value)} className="sm:max-w-xs" />
        <select aria-label="Status filtern" className={`${selectClass} sm:max-w-[200px]`} value={status} onChange={(e) => setStatus(e.target.value as StaffingAssignmentStatus | "")}>
          <option value="">Alle Status</option>
          {(Object.keys(ASSIGNMENT_STATUS_LABELS) as StaffingAssignmentStatus[]).map((key) => (
            <option key={key} value={key}>{ASSIGNMENT_STATUS_LABELS[key]}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-brand-soft">
          <input type="checkbox" checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} />
          Nur überfällige
        </label>
      </div>
      {error ? (
        <LoadError onRetry={() => void mutate()} />
      ) : isLoading || !data ? (
        <LoadingRows />
      ) : rows.length === 0 ? (
        <EmptyHint>{data.data.length === 0 ? "Noch keine Einsätze angelegt." : "Keine Einsätze zu diesem Filter."}</EmptyHint>
      ) : (
        <ul className="space-y-2">
          {rows.map((a) => (
            <li key={a.id}>
              <Link href={`/ueberlassung/einsaetze/${a.id}`} className="flex flex-col gap-2 rounded-lg border border-white/10 p-3 transition-colors hover:bg-brand-hover/40 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{a.worker_name} <span className="text-brand-muted">bei</span> {a.client_name}</p>
                  <p className="truncate text-xs text-brand-muted">
                    {formatDate(a.start_date)} – {a.actual_end_date ? formatDate(a.actual_end_date) : a.planned_end_date ? formatDate(a.planned_end_date) : "offen"}
                    {a.activity ? ` · ${a.activity}` : ""}{a.location ? ` · ${a.location}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-brand-muted">
                  {a.is_overdue && <Badge tone="red" title="Geplantes Ende überschritten – beenden oder verlängern">Überfällig</Badge>}
                  <span>Checkliste {a.checklist_done}/{a.checklist_total}</span>
                  <AssignmentStatusBadge status={a.status} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
