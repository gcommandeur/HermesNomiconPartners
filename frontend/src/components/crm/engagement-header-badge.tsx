"use client";

// NOMICON: Badge im Kandidatenkopf (Client-Insel in der Server-Seite).
import { EngagementBadge } from "@/components/crm/engagement-badge";
import { useEngagement } from "@/lib/api/engagement-hooks";

export function EngagementHeaderBadge({ candidateId }: { candidateId: string }) {
  const { data } = useEngagement(candidateId);
  return <EngagementBadge summary={data?.data} />;
}
