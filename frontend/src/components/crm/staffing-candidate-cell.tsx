// NOMICON: Zelle "Überlassung" der Kandidatenliste: Status, aktueller Kunde, Warnsymbol bei gelber/roter Frist.
import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { CANDIDATE_STAFFING_STATUS_LABELS, type StaffingCandidateSummary } from "@/lib/api/staffing";
import { staffingCandidateText, staffingWarning } from "@/lib/staffing-candidate";

export { staffingCandidateText };

const TONE = { none: "gray", applicant: "blue", active: "green", dormant: "amber", left: "gray" } as const;

export function StaffingCandidateCell({ summary, compact = false }: { summary: StaffingCandidateSummary | undefined; compact?: boolean }) {
  if (!summary || summary.status === "none") return compact ? null : <span className="text-xs text-brand-muted">–</span>;
  const warning = staffingWarning(summary);
  return (
    <div className={compact ? "mt-1.5 flex flex-wrap items-center gap-1.5" : "flex flex-col items-start gap-1"}>
      <Badge tone={TONE[summary.status]}>{CANDIDATE_STAFFING_STATUS_LABELS[summary.status]}</Badge>
      {summary.status === "active" && summary.client_name && <span className="max-w-[12rem] truncate text-[10.45px] text-brand-muted" title={summary.client_name}>{summary.client_name}</span>}
      {summary.bench && <span className="text-[10.45px] text-brand-muted">Bench</span>}
      {warning && (
        <span className={`inline-flex items-center gap-1 text-[10.45px] ${summary.traffic === "red" ? "text-brand-danger" : "text-brand-warning"}`} title={warning}>
          <AlertTriangle size={12} aria-hidden />{warning}
        </span>
      )}
    </div>
  );
}
