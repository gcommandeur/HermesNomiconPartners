import { Plus } from "lucide-react";
import { ExportActions } from "@/components/crm/export-actions";
import { PageHeader } from "@/components/crm/page-header";
import { VacanciesView } from "@/components/crm/vacancies-view";
import { DemoNotice } from "@/components/crm/demo-notice";
import { Button } from "@/components/ui/button";
import { getCandidates, getClients, getVacancies } from "@/lib/api/queries";

function salaryRange(min: number | null, max: number | null): string {
  if (min == null && max == null) return "—";
  const format = (value: number) => value.toLocaleString("de-DE");
  if (min != null && max != null) return `${format(min)}–${format(max)} EUR`;
  return `${format((min ?? max) as number)} EUR`;
}

export const dynamic = "force-dynamic";

export default async function VacanciesPage() {
  const [vacancies, clients, candidates] = await Promise.all([getVacancies(), getClients(), getCandidates()]);
  const clientName = (id: string | null) => id ? clients.data.find((client) => client.id === id)?.name ?? "Kanzlei" : "Optional / offen";
  const exportRows = vacancies.data.map((vacancy) => ({
    Titel: vacancy.title,
    Kanzlei: clientName(vacancy.client_company_id),
    Standort: vacancy.location,
    Status: vacancy.status,
    Prioritaet: vacancy.priority,
    Gehalt: salaryRange(vacancy.salary_min, vacancy.salary_max),
  }));

  return (
    <>
      <PageHeader
        eyebrow="Rollen und Suchprofile"
        title="Vakanzen"
        action={<div className="flex flex-wrap gap-2"><ExportActions filename="vakanzen" rows={exportRows} /><Button><Plus size={15} />Vakanz anlegen</Button></div>}
      />
      <DemoNotice source={vacancies.source === "api" && clients.source === "api" ? "api" : "demo"} />
      <VacanciesView vacancies={vacancies.data} clients={clients.data} candidates={candidates.data} />
    </>
  );
}
