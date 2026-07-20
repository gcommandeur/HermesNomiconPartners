import type { SearchSelectOption } from "@/components/ui/search-select";
import { getCandidatesPage, getClientsPage } from "./queries";

/** Serverseitige Suche fuer SearchSelect-Dropdowns (Kandidat/Kanzlei) - laedt
 * NICHT den kompletten Bestand vor (siehe use-server-search.ts), sondern
 * jeweils nur die Top-50-Treffer fuer den aktuellen Suchbegriff. Geteilt
 * zwischen submission-create-modal.tsx und calendar-event-modal.tsx. */
export async function searchCandidates(query: string): Promise<SearchSelectOption[]> {
  const result = await getCandidatesPage({ search: query || undefined, limit: 50, offset: 0 });
  return result.data.items.map((candidate) => ({
    value: candidate.id,
    label: `${candidate.first_name} ${candidate.last_name}`,
    sublabel: candidate.candidate_number ? `Nr. ${candidate.candidate_number}` : undefined,
  }));
}

export async function searchClients(query: string): Promise<SearchSelectOption[]> {
  const result = await getClientsPage({ search: query || undefined, limit: 50, offset: 0 });
  return result.data.items
    .filter((client) => client.status !== "blocked")
    .map((client) => ({
      value: client.id,
      label: client.name,
      sublabel: client.kanzleigruppe ?? client.city ?? undefined,
    }));
}
