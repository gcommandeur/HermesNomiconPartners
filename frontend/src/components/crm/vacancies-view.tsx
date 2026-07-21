"use client";

import { useMemo, useState } from "react";
import { BrainCircuit, BriefcaseBusiness } from "lucide-react";
import { FilterBar } from "@/components/crm/filter-bar";
import { DataTable } from "@/components/crm/data-table";
import { StatusPill } from "@/components/crm/status-pill";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { Candidate, ClientCompany, Vacancy } from "@/lib/api/types";

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

export function VacanciesView({ vacancies, clients, candidates }: {
  vacancies: Vacancy[];
  clients: ClientCompany[];
  candidates: Candidate[];
}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const clientName = (id: string | null) => id ? clients.find((client) => client.id === id)?.name ?? "Kanzlei" : "Optional / offen";
  const matchCount = (qualification: string | null) => candidates.filter((candidate) => `${candidate.summary ?? ""} ${candidate.job_title ?? ""}`.toLowerCase().includes((qualification ?? "tax").split(" ")[0].toLowerCase())).length;

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
        placeholder="Nach Rolle, Kanzlei, Standort, Gehalt oder Arbeitsmodell suchen"
        value={search}
        onChange={setSearch}
        statusOptions={STATUS_OPTIONS}
        statusValue={status}
        onStatusChange={setStatus}
      />
      <section className="mb-5 grid grid-cols-1 gap-3 lg:grid-cols-3">
        {filtered.map((vacancy) => (
          <Card key={vacancy.id}>
            <CardHeader><div><div className="flex items-center gap-2"><BriefcaseBusiness size={16} className="text-[#D8DADF]" /><h2 className="font-semibold">{vacancy.title}</h2></div><p className="mt-1 text-xs text-[#94A3B8]">{clientName(vacancy.client_company_id)} · {vacancy.location}</p></div><StatusPill status={vacancy.status} /></CardHeader>
            <CardContent>
              <p className="text-sm leading-6 text-[#CBD5E1]">{vacancy.description}</p>
              <div className="mt-4 flex flex-wrap gap-1.5">{[...vacancy.must_have, ...vacancy.nice_to_have.slice(0, 2)].map((tag) => <span key={tag} className="rounded bg-[#102A4C]/70 px-2 py-1 text-[10px] text-[#CBD5E1]">{tag}</span>)}</div>
              <div className="mt-4 rounded-lg border border-[#1F5FA8]/25 bg-[#102A4C]/45 p-3 text-xs text-[#CBD5E1]"><BrainCircuit size={14} className="mb-2 text-[#69A7EA]" />Regelbasiertes Matching vorbereitet: {matchCount(vacancy.qualifications)} mögliche Kandidaten. AI-Begründung folgt mit Agenten-/KI-Anbindung.</div>
            </CardContent>
          </Card>
        ))}
        {filtered.length === 0 && <Card><CardContent className="py-12 text-center text-sm text-[#858b90]">Keine Vakanzen gefunden.</CardContent></Card>}
      </section>
      <DataTable headers={["Vakanz", "Kanzlei", "Standort", "Umkreis", "Qualifikation", "Gehalt", "Arbeitsmodell", "Status", "Priorität"]}>
        {filtered.map((vacancy) => (
          <tr key={vacancy.id} className="hover:bg-[#203A5A]/35">
            <td className="px-4 py-3.5 font-semibold text-[#D8DADF]">{vacancy.title}</td>
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
      <p className="mt-3 text-xs text-[#8a9095]">{filtered.length} von {vacancies.length} Vakanzen</p>
    </>
  );
}
