"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPatch, apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import type { ClientCompany, Vacancy } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-brand-muted";
const textareaClass = "min-h-20 w-full rounded-md border border-white/10 bg-brand-surface p-3 text-sm text-brand-text outline-none focus:border-brand-accent";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-brand-surface px-3 text-sm text-brand-text outline-none focus:border-brand-accent";

const emptyForm = {
  title: "",
  client_company_id: "",
  location: "",
  status: "draft",
  priority: "normal",
  search_radius_km: "30",
  work_model: "",
  qualifications: "",
  experience: "",
  description: "",
  must_have: "",
  nice_to_have: "",
  salary_min: "",
  salary_max: "",
  fee_percentage: "",
};

function formFromVacancy(vacancy: Vacancy): typeof emptyForm {
  return {
    title: vacancy.title,
    client_company_id: vacancy.client_company_id ?? "",
    location: vacancy.location ?? "",
    status: vacancy.status,
    priority: vacancy.priority,
    search_radius_km: String(vacancy.search_radius_km ?? 30),
    work_model: vacancy.work_model ?? "",
    qualifications: vacancy.qualifications ?? "",
    experience: vacancy.experience ?? "",
    description: vacancy.description ?? "",
    must_have: vacancy.must_have.join(", "),
    nice_to_have: vacancy.nice_to_have.join(", "),
    salary_min: vacancy.salary_min != null ? String(vacancy.salary_min) : "",
    salary_max: vacancy.salary_max != null ? String(vacancy.salary_max) : "",
    fee_percentage: vacancy.fee_percentage != null ? String(vacancy.fee_percentage) : "",
  };
}

function VacancyForm({
  clients,
  vacancy,
  onDone,
}: {
  clients: ClientCompany[];
  vacancy?: Vacancy;
  onDone: (vacancy: Vacancy) => void;
}) {
  const router = useRouter();
  const isEdit = Boolean(vacancy);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState(vacancy ? formFromVacancy(vacancy) : emptyForm);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const payload = {
        title: form.title,
        client_company_id: form.client_company_id || null,
        location: form.location.trim() || null,
        status: form.status,
        priority: form.priority,
        search_radius_km: Number(form.search_radius_km) || 0,
        work_model: form.work_model.trim() || null,
        qualifications: form.qualifications.trim() || null,
        experience: form.experience.trim() || null,
        description: form.description.trim() || null,
        must_have: form.must_have.split(",").map((item) => item.trim()).filter(Boolean),
        nice_to_have: form.nice_to_have.split(",").map((item) => item.trim()).filter(Boolean),
        salary_min: form.salary_min.trim() ? Number(form.salary_min) : null,
        salary_max: form.salary_max.trim() ? Number(form.salary_max) : null,
        fee_percentage: form.fee_percentage.trim() ? Number(form.fee_percentage) : null,
      };
      const result = isEdit
        ? await apiPatch<Vacancy>(`/vacancies/${vacancy!.id}`, payload)
        : await apiPost<Vacancy>("/vacancies", payload);
      onDone(result);
      router.refresh();
    } catch (exception) {
      setError(
        exception instanceof Error
          ? exception.message
          : isEdit
            ? "Änderungen konnten nicht gespeichert werden."
            : "Vakanz konnte nicht angelegt werden.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div><label className={labelClass}>Titel *</label><Input required value={form.title} onChange={(e) => set("title", e.target.value)} /></div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className={labelClass}>Kanzlei</label>
          <select className={selectClass} value={form.client_company_id} onChange={(e) => set("client_company_id", e.target.value)}>
            <option value="">Optional / offen</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div><label className={labelClass}>Standort</label><Input placeholder="z.B. 80331 München" value={form.location} onChange={(e) => set("location", e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label className={labelClass}>Status</label>
          <select className={selectClass} value={form.status} onChange={(e) => set("status", e.target.value)}>
            <option value="draft">Entwurf</option>
            <option value="open">Offen</option>
            <option value="on_hold">Pausiert</option>
            <option value="filled">Besetzt</option>
            <option value="closed">Geschlossen</option>
          </select>
        </div>
        <div>
          <label className={labelClass}>Priorität</label>
          <select className={selectClass} value={form.priority} onChange={(e) => set("priority", e.target.value)}>
            <option value="low">Niedrig</option>
            <option value="normal">Normal</option>
            <option value="high">Hoch</option>
            <option value="urgent">Dringend</option>
          </select>
        </div>
        <div><label className={labelClass}>Umkreis (km)</label><Input type="number" min={0} max={500} value={form.search_radius_km} onChange={(e) => set("search_radius_km", e.target.value)} /></div>
      </div>
      <div><label className={labelClass}>Arbeitsmodell</label><Input placeholder="z.B. Remote, Hybrid, Vor Ort" value={form.work_model} onChange={(e) => set("work_model", e.target.value)} /></div>
      <div><label className={labelClass}>Qualifikationen</label><textarea className={textareaClass} value={form.qualifications} onChange={(e) => set("qualifications", e.target.value)} /></div>
      <div><label className={labelClass}>Erfahrung</label><textarea className={textareaClass} value={form.experience} onChange={(e) => set("experience", e.target.value)} /></div>
      <div><label className={labelClass}>Beschreibung</label><textarea className={textareaClass} value={form.description} onChange={(e) => set("description", e.target.value)} /></div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div><label className={labelClass}>Must-have (Komma-getrennt)</label><Input placeholder="z.B. Steuerberater, Umsatzsteuer" value={form.must_have} onChange={(e) => set("must_have", e.target.value)} /></div>
        <div><label className={labelClass}>Nice-to-have (Komma-getrennt)</label><Input placeholder="z.B. DATEV, M&A" value={form.nice_to_have} onChange={(e) => set("nice_to_have", e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div><label className={labelClass}>Gehalt von</label><Input type="number" min={0} value={form.salary_min} onChange={(e) => set("salary_min", e.target.value)} /></div>
        <div><label className={labelClass}>Gehalt bis</label><Input type="number" min={0} value={form.salary_max} onChange={(e) => set("salary_max", e.target.value)} /></div>
        <div><label className={labelClass}>Honorar (%)</label><Input type="number" min={0} max={100} step="0.01" value={form.fee_percentage} onChange={(e) => set("fee_percentage", e.target.value)} /></div>
      </div>
      <ErrorBanner message={error} />
      <div className="flex justify-end gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Speichern…" : isEdit ? "Änderungen speichern" : "Vakanz anlegen"}
        </Button>
      </div>
    </form>
  );
}

export function VacancyCreateModal({ clients, onCreated }: { clients: ClientCompany[]; onCreated?: (vacancy: Vacancy) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}><Plus size={15} />Vakanz anlegen</Button>
      {open && (
        <Modal title="Vakanz anlegen" eyebrow="Rollen und Suchprofile" onClose={() => setOpen(false)}>
          <VacancyForm clients={clients} onDone={(vacancy) => { setOpen(false); onCreated?.(vacancy); }} />
        </Modal>
      )}
    </>
  );
}

export function VacancyEditModal({
  vacancy,
  clients,
  onUpdated,
}: {
  vacancy: Vacancy;
  clients: ClientCompany[];
  onUpdated?: (vacancy: Vacancy) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}><Pencil size={13} />Bearbeiten</Button>
      {open && (
        <Modal title="Vakanz bearbeiten" eyebrow="Rollen und Suchprofile" onClose={() => setOpen(false)}>
          <VacancyForm clients={clients} vacancy={vacancy} onDone={(updated) => { setOpen(false); onUpdated?.(updated); }} />
        </Modal>
      )}
    </>
  );
}
