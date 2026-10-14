"use client";

// NOMICON: kleines Badge "wo ist der Kandidat bereits im Austausch" (Liste, Suche, Kopf).
import { Badge } from "@/components/ui/badge";
import {
  ENGAGEMENT_STATUS_LABELS,
  stageLabel,
  type CandidateEngagement,
  type EngagementItem,
} from "@/lib/api/engagement";
import { formatDate } from "@/lib/utils";

/** Mitarbeitername kurz: bei E-Mail-Adressen nur der Teil vor dem @. */
function shortName(name: string): string {
  return name.includes("@") ? name.split("@")[0] : name;
}

function itemText(item: EngagementItem): string {
  const channel = item.channel === "direct" ? "Direct" : "AÜ";
  const who = item.owner_name ? ` (${shortName(item.owner_name)})` : "";
  return `${channel}: ${stageLabel(item.stage)}${who}`;
}

/** Zeile je Prozess/Einsatz für Tooltip und Zeitlinie; Kanzlei nur, wenn sie sichtbar ist. */
export function itemDetail(item: EngagementItem): string {
  const since = item.since ? ` seit ${formatDate(item.since)}` : "";
  const until = item.until ? `, bis ${formatDate(item.until)}` : "";
  const client = item.details_visible && item.client_name ? ` · ${item.client_name}` : "";
  return `${itemText(item)}${since}${until}${client}`;
}

export function engagementLabel(summary: CandidateEngagement): string {
  const direct = summary.items.find((item) => item.channel === "direct");
  const staffing = summary.items.find((item) => item.channel === "staffing");
  switch (summary.status) {
    case "frei":
      return ENGAGEMENT_STATUS_LABELS.frei;
    case "im_direct":
      return direct ? itemText(direct) : ENGAGEMENT_STATUS_LABELS.im_direct;
    case "im_einsatz":
      return staffing ? itemText(staffing) : ENGAGEMENT_STATUS_LABELS.im_einsatz;
    case "beides":
      return ENGAGEMENT_STATUS_LABELS.beides;
    case "vermittelt":
      return ENGAGEMENT_STATUS_LABELS.vermittelt;
  }
}

const TONES = {
  frei: "green",
  im_direct: "blue",
  im_einsatz: "blue",
  beides: "amber",
  vermittelt: "gray",
} as const;

export function EngagementBadge({ summary, className }: { summary: CandidateEngagement | undefined; className?: string }) {
  if (!summary) return null;
  const title = summary.items.length > 0 ? summary.items.map(itemDetail).join("\n") : "Aktuell in keinem Prozess und keinem Einsatz.";
  return (
    <Badge tone={TONES[summary.status]} title={title} className={`max-w-[13rem] whitespace-nowrap ${className ?? ""}`}>
      <span className="truncate">{engagementLabel(summary)}</span>
    </Badge>
  );
}
