"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { BriefcaseBusiness, Trash2 } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { StatusPill } from "@/components/crm/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { apiDelete } from "@/lib/api/client";
import { VacancyEditModal } from "@/components/crm/vacancy-create-modal";
import { VacancyMatchingPanel } from "@/components/crm/vacancy-matching-panel";
import type { ClientCompany, Vacancy } from "@/lib/api/types";

const STATUS_OPTIONS = [
  { value: "open", label: "Offen" },
  { value: "draft", label: "Entwurf" },
  { value: "on_hold", label: "Pausiert" },
  { value: "filled", label: "Besetzt" },
  { value: "closed", label: "Geschlossen" },
];

function salaryRange(min: number | null, max: number | null): string {
  if (min == null && max == null) return "—";
  const format = (value: number) => value.toLocaleString("de-DE");
  if (min != null && max != null) return `${format(min)}–${format(max)} EUR`;
  return `${format((min ?? max) as number)} EUR`;
}

export function VacanciesView({ vacancies, clients }: {
  vacancies: Vacancy[];
  clients: ClientCompany[];
}) {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const clientName = (id: string | null) => id ? clients.find((client) => client.id === id)?.name ?? "Kunde" : "Optional / offen";

  async function handleDelete(vacancy: Vacancy) {
    if (!window.confirm(`Vakanz "${vacancy.title}" wirklich löschen?`)) return;
    setDeletingId(vacancy.id);
    try {
      await apiDelete(`/vacancies/${vacancy.id}`);
      router.refresh();
    } finally {
      setDeletingId(null);
    }
  }

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return vacancies.filter((vacancy) => {
      if (status && vacancy.status !== status) return false;
      if (!term) return true;
      const haystack = [
        vacancy.title, clientName(vacancy.client_company_id), vacancy.location,
        vacancy.qualifications, vacancy.work_model,
      ].filter(Boolean).join(" ").toLowerCase();
      return haystack.includes(term);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vacancies, search, status, clients]);

  return (
    <>
      <FilterBar
        placeholder="Nach Rolle, Kunde, Standort, Gehalt oder Arbeitsmodell suchen"
        value={search}
        onChange={setSearch}
        statusOptions={STATUS_OPTIONS}
        statusValue={status}
        onStatusChange={setStatus}
      />
      <section className="mb-5 grid grid-cols-1 gap-3 lg:grid-cols-3">
        {filtered.map((vacancy) => (
          <Card key={vacancy.id}>
            <CardHeader>
              <div>
                <div className="flex items-center gap-2"><BriefcaseBusiness size={16} className="text-brand-platinum" /><h2 className="font-semibold">{vacancy.title}</h2></div>
                <p className="mt-1 text-xs text-brand-muted">{clientName(vacancy.client_company_id)} · {vacancy.location}</p>
              </div>
              <StatusPill status={vacancy.status} />
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-6 text-brand-soft">{vacancy.description}</p>
              <div className="mt-4 flex flex-wrap gap-1.5">{[...vacancy.must_have, ...vacancy.nice_to_have.slice(0, 2)].map((tag) => <span key={tag} className="rounded bg-brand-accent-soft/70 px-2 py-1 text-[9.5px] text-brand-soft">{tag}</span>)}</div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Button size="sm" variant="outline" onClick={() => setExpandedId((current) => (current === vacancy.id ? null : vacancy.id))}>
                  {expandedId === vacancy.id ? "Matching ausblenden" : "Passende Kandidaten anzeigen"}
                </Button>
                <VacancyEditModal vacancy={vacancy} clients={clients} />
                <Button size="sm" variant="outline" disabled={deletingId === vacancy.id} onClick={() => handleDelete(vacancy)}>
                  <Trash2 size={13} />{deletingId === vacancy.id ? "Lösche…" : "Löschen"}
                </Button>
              </div>
              {expandedId === vacancy.id && (
                <div className="mt-4">
                  <VacancyMatchingPanel vacancyId={vacancy.id} />
                </div>
              )}
            </CardContent>
          </Card>
        ))}
        {filtered.length === 0 && <Card><CardContent className="py-12 text-center text-sm text-brand-gray">Keine Vakanzen gefunden.</CardContent></Card>}
      </section>
      {/* Nur ab lg: die Kartenansicht oben deckt Mobile bereits vollstaendig
       * ab (grid-cols-1) - diese Tabelle darunter zeigt dieselben Vakanzen
       * nur mit ein paar Zusatzspalten (Umkreis/Prioritaet) und war auf
       * einem Telefon nur horizontal scrollbar erreichbar (Nutzer-Feedback
       * "mobile Version nicht passend"). */}
      <div className="hidden lg:block">
      <DataTable headers={["Vakanz", "Kunde", "Standort", "Umkreis", "Qualifikation", "Gehalt", "Arbeitsmodell", "Status", "Priorität"]}>
        {filtered.map((vacancy) => (
          <tr key={vacancy.id} className="hover:bg-brand-hover/35">
            <td className="px-4 py-3.5 font-semibold text-brand-platinum">{vacancy.title}</td>
            <td className="px-4 py-3.5">{clientName(vacancy.client_company_id)}</td>
            <td className="px-4 py-3.5">{vacancy.location}</td>
            <td className="px-4 py-3.5">{vacancy.search_radius_km ? `${vacancy.search_radius_km} km` : "—"}</td>
            <td className="px-4 py-3.5">{vacancy.qualifications}</td>
            <td className="px-4 py-3.5">{salaryRange(vacancy.salary_min, vacancy.salary_max)}</td>
            <td className="px-4 py-3.5">{vacancy.work_model}</td>
            <td className="px-4 py-3.5"><StatusPill status={vacancy.status} /></td>
            <td className="px-4 py-3.5"><StatusPill status={vacancy.priority} /></td>
          </tr>
        ))}
      </DataTable>
      </div>
      <p className="mt-3 text-xs text-brand-gray">{filtered.length} von {vacancies.length} Vakanzen</p>
    </>
  );
}
