"use client";

import useSWR, { mutate } from "swr";
import { Hourglass } from "lucide-react";
import { getPendingApprovalsFor } from "@/lib/api/queries";
import type { ApprovalRequest } from "@/lib/api/types";

type EntityType = "client_company" | "fee";

const pendingKey = (entityType: EntityType, entityId: string) =>
  `/approval-requests/for/${entityType}/${entityId}`;

/** Nach dem Speichern aufrufen, damit der Hinweis sofort erscheint/verschwindet. */
export function invalidatePendingApprovals(entityType: EntityType, entityId: string) {
  return mutate(pendingKey(entityType, entityId));
}

function describe(request: ApprovalRequest): string {
  if (request.kind === "new_client") return "Neue Kanzlei – wartet auf Freigabe durch die Geschäftsführung";
  if (request.kind === "invoice_issue") return "Rechnung stellen – wartet auf Freigabe durch die Geschäftsführung";
  const changes = Object.entries(request.proposed_values ?? {})
    .map(([key, value]) => `${key === "fee_percentage" ? "Honorar" : key}: ${String(request.old_values?.[key] ?? "—")} → ${String(value ?? "—")}`)
    .join(", ");
  return `Honorar-Änderung wartet auf Freigabe (${changes}) – bis dahin gelten die bisherigen Konditionen`;
}

export function ApprovalPendingNotice({ entityType, entityId }: { entityType: EntityType; entityId: string }) {
  const { data } = useSWR(pendingKey(entityType, entityId), () => getPendingApprovalsFor(entityType, entityId), {
    revalidateOnFocus: false,
  });
  const pending = data?.data ?? [];
  if (pending.length === 0) return null;
  return (
    <div className="mt-3 space-y-1.5">
      {pending.map((request) => (
        <p
          key={request.id}
          className="flex items-start gap-2 rounded-md border border-[#F0B429]/30 bg-[#F0B429]/10 px-3 py-2 text-xs text-[#F0B429]"
        >
          <Hourglass size={13} className="mt-0.5 shrink-0" />
          {describe(request)}
        </p>
      ))}
    </div>
  );
}
