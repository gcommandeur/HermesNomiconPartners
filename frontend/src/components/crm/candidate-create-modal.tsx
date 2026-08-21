"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Pencil, Plus, Sparkles, Trash2, Upload } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPatch, apiPost, apiUpload } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import { invalidateCandidatesCache, useAssignableUsersCache, useCurrentUser } from "@/lib/api/hooks";
import { NOTICE_PERIOD_OPTIONS, NOTICE_PERIOD_OTHER } from "@/lib/utils";
import type { BeruflicheStation, Candidate, CvExtractionSuggestion } from "@/lib/api/types";

// Ordnet die vom Backend erkannten CV-Felder (siehe
// cc_crm.services.cv_extraction.extract_candidate_fields) den passenden
// Formularfeldern zu - nur fuer Felder, die es auch im Anlegen-Formular gibt.
// (source_is_agency_profile bewusst ausgeschlossen: kein Formularfeld, kein string.)
type CvStringSuggestionField = Exclude<keyof CvExtractionSuggestion, "source_is_agency_profile">;
const CV_SUGGESTION_TO_FORM_FIELD: Array<[CvStringSuggestionField, keyof typeof emptyForm]> = [
  ["first_name", "first_name"],
  ["last_name", "last_name"],
  ["email", "email"],
  ["postal_code", "postal_code"],
  ["city", "city"],
  ["phone", "phone"],
  ["job_title", "job_title"],
  ["qualification", "qualification"],
  ["ausbildung_titel", "ausbildung_titel"],
];

// Anzeige-Labels fuer das "was wurde uebernommen"-Panel unten - gleiche
// Reihenfolge/Feldauswahl wie CV_SUGGESTION_TO_FORM_FIELD.
const CV_FIELD_LABELS: Record<CvStringSuggestionField, string> = {
  first_name: "Vorname",
  last_name: "Nachname",
  email: "E-Mail",
  postal_code: "PLZ",
  city: "Ort",
  phone: "Telefon",
  job_title: "Rolle",
  qualification: "Qualifikation",
  ausbildung_titel: "Ausbildung/Weiterbildung",
};

const labelClass = "mb-1 block text-xs text-[#94A3B8]";
const textareaClass = "min-h-20 w-full rounded-md border border-white/10 bg-[#0D1B2E] p-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";
const internClass = "mb-1 flex items-center gap-1.5 text-xs text-[#F0B429]";

const emptyForm = {
  candidate_number: "", first_name: "", last_name: "", email: "", phone: "", job_title: "", anrede: "",
  status: "active",
  qualification: "", postal_code: "", city: "", salary_expectation: "", notice_period: "",
  fachliche_schwerpunkte: "", ausbildung_titel: "",
  aktuelles_umfeld_kanzleityp: "", aktuelles_umfeld_kanzleigroesse: "",
  remote_teilzeit_wuensche: "", passender_kanzleityp: "",
  wechselgrund: "", no_gos: "", freitext_notizen: "", referred_by: "",
  owner_user_id: "",
};

function formFromCandidate(candidate: Candidate): typeof emptyForm {
  return {
    candidate_number: candidate.candidate_number ?? "",
    first_name: candidate.first_name ?? "",
    last_name: candidate.last_name ?? "",
    email: candidate.email ?? "",
    phone: candidate.phone ?? "",
    job_title: candidate.job_title ?? "",
    anrede: candidate.anrede ?? "",
    status: candidate.status ?? "active",
    qualification: candidate.qualification ?? "",
    postal_code: candidate.postal_code ?? "",
    city: candidate.city ?? "",
    salary_expectation: candidate.salary_expectation ?? "",
    notice_period: candidate.notice_period ?? "",
    fachliche_schwerpunkte: (candidate.fachliche_schwerpunkte ?? []).join(", "),
    ausbildung_titel: candidate.ausbildung_titel ?? "",
    aktuelles_umfeld_kanzleityp: candidate.aktuelles_umfeld_kanzleityp ?? "",
    aktuelles_umfeld_kanzleigroesse: candidate.aktuelles_umfeld_kanzleigroesse ?? "",
    remote_teilzeit_wuensche: candidate.remote_teilzeit_wuensche ?? "",
    passender_kanzleityp: candidate.passender_kanzleityp ?? "",
    wechselgrund: candidate.wechselgrund ?? "",
    no_gos: (candidate.no_gos ?? []).join(", "),
    freitext_notizen: candidate.freitext_notizen ?? "",
    referred_by: candidate.referred_by ?? "",
    owner_user_id: candidate.owner_user_id ?? "",
  };
}

const emptyStation: BeruflicheStation = { kanzleityp: "", kanzleigroesse: "", dauer_jahre: 0 };

/** Dropdown mit den gaengigen Kuendigungsfrist-Kombinationen + "Sonstige"
 * (Freitext) statt eines reinen Input - siehe NOTICE_PERIOD_OPTIONS in
 * lib/utils.ts. `value`/`onChange` binden weiterhin direkt an den
 * tatsaechlichen notice_period-String (Backend bleibt Freitext) - "Sonstige"
 * ist nur ein UI-Sentinel, kein gespeicherter Wert. Ein Bestandswert, der
 * keiner Option exakt entspricht, klappt automatisch das Freitextfeld mit
 * dem Originaltext auf, statt ihn stillschweigend zu verwerfen. */
function NoticePeriodField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  // Ein leerer value laesst sich NICHT aus value allein zwischen "keine
  // Angabe" und "Sonstige frisch gewaehlt, Freitext noch leer" unterscheiden
  // (value ist in beiden Faellen "") - deshalb zusaetzlich eigener State, nur
  // fuer den bewussten Wechsel in den Sonstige-Modus. Ein Bestandswert, der
  // beim Laden schon nicht-leer und keine bekannte Option ist, gilt ueber
  // isKnownOption unten automatisch als Sonstige, ganz ohne diesen State.
  const [otherSelected, setOtherSelected] = useState(false);
  const isKnownOption = NOTICE_PERIOD_OPTIONS.includes(value);
  const showOther = otherSelected || (!isKnownOption && value !== "");
  const selectValue = showOther ? NOTICE_PERIOD_OTHER : value;

  return (
    <div>
      <select
        className={selectClass}
        value={selectValue}
        onChange={(e) => {
          const next = e.target.value;
          if (next === NOTICE_PERIOD_OTHER) {
            // Freitextfeld startet leer, nicht mit dem vorherigen
            // Optionstext.
            setOtherSelected(true);
            onChange("");
          } else {
            setOtherSelected(false);
            onChange(next);
          }
        }}
      >
        <option value="">Keine Angabe</option>
        {NOTICE_PERIOD_OPTIONS.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
        <option value={NOTICE_PERIOD_OTHER}>Sonstige</option>
      </select>
      {showOther && (
        <Input
          className="mt-2"
          placeholder="Kündigungsfrist frei eingeben"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}

export function CandidateCreateForm({
  onDone,
  candidate,
}: {
  onDone: (candidate: Candidate) => void;
  candidate?: Candidate;
}) {
  const router = useRouter();
  const isEdit = Boolean(candidate);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState(candidate ? formFromCandidate(candidate) : emptyForm);
  const [stations, setStations] = useState<BeruflicheStation[]>(candidate?.berufliche_stationen ?? []);
  const { data: currentUserData } = useCurrentUser();
  const { data: assignableUsersData } = useAssignableUsersCache();
  const assignableUsers = assignableUsersData?.data ?? [];
  // Default = aktuell eingeloggter Nutzer (aber im Dropdown aenderbar) - nur
  // beim Neuanlegen, im Bearbeiten-Modus bleibt der bestehende Owner stehen.
  const ownerUserId = form.owner_user_id || (isEdit ? "" : currentUserData?.data.id ?? "");

  // CV-Upload direkt im Anlegen-Formular (Nutzer-Feedback: "keine Option
  // einen CV hinzuzufuegen, weder per Upload noch per Drag&Drop") - die
  // Datei wird hier nur ausgelesen, um leere Felder vorzubefuellen; der
  // eigentliche Dokument-Upload passiert erst nach erfolgreichem Anlegen
  // (siehe handleSubmit), da vorher keine candidate_id existiert.
  const [cvFile, setCvFile] = useState<File | null>(null);
  const [cvExtracting, setCvExtracting] = useState(false);
  const [cvError, setCvError] = useState<string | null>(null);
  // Fuer das sichtbare "was wurde uebernommen"-Panel - Nutzer-Feedback:
  // "Auslesen klappt nur auf dem Feld, nicht direkt auf dem Bildschirm"
  // (der einzeilige Hinweistext zuvor war offenbar nicht auffaellig genug).
  const [cvAppliedFields, setCvAppliedFields] = useState<Array<{ label: string; value: string }>>([]);
  const [dragActive, setDragActive] = useState(false);
  const dragCounter = useRef(0);
  const cvInputRef = useRef<HTMLInputElement>(null);

  function set<K extends keyof typeof form>(key: K, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function setStation<K extends keyof BeruflicheStation>(index: number, key: K, value: BeruflicheStation[K]) {
    setStations((current) => current.map((station, i) => (i === index ? { ...station, [key]: value } : station)));
  }

  async function handleCvFile(file: File) {
    setCvFile(file);
    setCvExtracting(true);
    setCvError(null);
    setCvAppliedFields([]);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const suggestion = await apiUpload<CvExtractionSuggestion>("/candidates/cv-preview", formData);
      const applied: Array<{ label: string; value: string }> = [];
      setForm((current) => {
        const updated = { ...current };
        for (const [suggestionKey, formKey] of CV_SUGGESTION_TO_FORM_FIELD) {
          const value = suggestion[suggestionKey];
          if (value && !current[formKey].trim()) {
            updated[formKey] = value;
            applied.push({ label: CV_FIELD_LABELS[suggestionKey], value });
          }
        }
        return updated;
      });
      setCvAppliedFields(applied);
    } catch (exception) {
      // Ausgelesene Felder sind reiner Komfort - schlaegt das Auslesen fehl
      // (z.B. kein Anthropic-Key konfiguriert), bleibt die Datei trotzdem
      // fuer den Upload nach dem Anlegen vorgemerkt.
      setCvError(exception instanceof Error ? exception.message : "CV konnte nicht ausgelesen werden.");
    } finally {
      setCvExtracting(false);
    }
  }

  function handleCvDragEnter(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (!event.dataTransfer.types.includes("Files")) return;
    dragCounter.current += 1;
    setDragActive(true);
  }

  function handleCvDragLeave(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragCounter.current = Math.max(0, dragCounter.current - 1);
    if (dragCounter.current === 0) setDragActive(false);
  }

  function handleCvDragOver(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
  }

  async function handleCvDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    dragCounter.current = 0;
    setDragActive(false);
    const file = event.dataTransfer.files?.[0];
    if (!file || cvExtracting) return;
    await handleCvFile(file);
  }

  async function handleCvInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    await handleCvFile(file);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Leere Felder werden zu null (gültig für optionale Enum-/E-Mail-Felder wie
      // anrede/email), statt als "" ans Backend geschickt zu werden - "" ist z.B.
      // kein gültiger anrede-Enum-Wert und wurde vom Backend mit 422 abgelehnt,
      // sobald im Bearbeiten-Modus gespeichert wurde (betraf praktisch jeden
      // importierten Kandidaten ohne gesetzte Anrede).
      const stringFields = Object.fromEntries(
        Object.entries(form)
          .filter(([, value]) => (isEdit ? true : value.trim() !== ""))
          .map(([key, value]) => [key, value.trim() === "" ? null : value]),
      );
      const payload = {
        ...stringFields,
        fachliche_schwerpunkte: form.fachliche_schwerpunkte
          .split(",").map((item) => item.trim()).filter(Boolean),
        no_gos: form.no_gos.split(",").map((item) => item.trim()).filter(Boolean),
        berufliche_stationen: stations.filter((station) => station.kanzleityp.trim() !== ""),
      };
      const result = isEdit
        ? await apiPatch<Candidate>(`/candidates/${candidate!.id}`, payload)
        : await apiPost<Candidate>("/candidates", payload);
      if (!isEdit) {
        setForm(emptyForm);
        setStations([]);
      }
      // War beim Anlegen bereits ein CV per Button/Drag&Drop ausgewaehlt,
      // wird es jetzt (erst jetzt existiert eine candidate_id) tatsaechlich
      // als Dokument hochgeladen - fehlschlagender Upload darf das
      // erfolgreiche Anlegen des Kandidaten nicht verdecken, daher separat
      // abgefangen statt den ganzen try-Block scheitern zu lassen.
      if (!isEdit && cvFile) {
        try {
          const uploadData = new FormData();
          uploadData.append("owner_type", "candidate");
          uploadData.append("owner_id", result.id);
          uploadData.append("document_type", "cv");
          uploadData.append("file", cvFile);
          await apiUpload("/documents/upload", uploadData);
        } catch {
          // Wird im Dokumente-Tab sichtbar sein, falls es doch fehlschlaegt -
          // der Nutzer landet dort ohnehin direkt danach.
        }
      }
      void invalidateCandidatesCache();
      onDone(result);
      if (isEdit) {
        router.refresh();
      } else {
        // Direkt zum Dokumente-Tab des neu angelegten Kandidaten - ohne
        // diesen Sprung gab es nach dem Anlegen keinen offensichtlichen
        // naechsten Schritt, um einen CV hochzuladen (Nutzer-Feedback:
        // "keine Option einen CV hinzuzufuegen").
        router.push(`/kandidaten/${result.id}?tab=Dokumente`);
      }
    } catch (exception) {
      setError(
        exception instanceof Error
          ? exception.message
          : isEdit
            ? "Änderungen konnten nicht gespeichert werden."
            : "Kandidat konnte nicht angelegt werden.",
      );
    } finally {
      setBusy(false);
    }
  }

  // Drag&Drop nur beim Neuanlegen aktiv - beim Bearbeiten gibt es dafuer
  // bereits den Dokumente-Tab (document-panel.tsx) am Kandidaten selbst.
  const cvDragHandlers = isEdit
    ? {}
    : {
        onDragEnter: handleCvDragEnter,
        onDragLeave: handleCvDragLeave,
        onDragOver: handleCvDragOver,
        onDrop: handleCvDrop,
      };

  return (
    <div className="relative" {...cvDragHandlers}>
      {dragActive && !isEdit && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-lg border-2 border-dashed border-[#1F5FA8] bg-[#0D1B2E]/90 text-sm font-semibold text-[#D8DADF]">
          CV hier ablegen…
        </div>
      )}
      <form className="space-y-4" onSubmit={handleSubmit}>
      {!isEdit && (
        <div className="rounded-lg border border-white/10 bg-[#0D1B2E]/75 p-3 text-xs text-[#94A3B8]">
          <div className="flex items-center justify-between gap-3">
            <span>CV hochladen, um Name/E-Mail/Rolle/Qualifikation/PLZ/Ort/Telefon/Ausbildung automatisch zu befüllen — oder Datei per Drag&Drop auf dieses Fenster ziehen.</span>
            <input ref={cvInputRef} type="file" className="hidden" onChange={handleCvInputChange} />
            <Button type="button" size="sm" variant="outline" onClick={() => cvInputRef.current?.click()} disabled={cvExtracting}>
              <Upload size={14} />
              {cvExtracting ? "Liest aus…" : "CV hochladen"}
            </Button>
          </div>
          {cvFile && !cvExtracting && !cvError && (
            <div className="mt-3 rounded-md border border-[#1F5FA8]/30 bg-[#102A4C]/50 p-2.5">
              <p className="flex items-center gap-1.5 font-semibold text-[#69A7EA]">
                <Sparkles size={13} />{cvFile.name} ausgelesen
              </p>
              {cvAppliedFields.length > 0 ? (
                <div className="mt-2 space-y-1">
                  {cvAppliedFields.map(({ label, value }) => (
                    <div key={label} className="flex items-center gap-2">
                      <span className="w-40 shrink-0 text-[#94A3B8]">{label}</span>
                      <span className="text-[#D8DADF]">{value}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-1 text-[#94A3B8]">Keine zusätzlichen Felder erkannt.</p>
              )}
            </div>
          )}
          {cvError && <p className="mt-2 text-[#F0B429]">{cvError}</p>}
        </div>
      )}
      {isEdit && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass}>Kandidatennummer</label><Input value={form.candidate_number} onChange={(e) => set("candidate_number", e.target.value)} /></div>
          <div>
            <label className={labelClass}>Status</label>
            <select className={selectClass} value={form.status} onChange={(e) => set("status", e.target.value)}>
              <option value="active">Aktiv</option>
              <option value="passive">Passiv</option>
              <option value="placed">Platziert</option>
              <option value="blocked">Gesperrt</option>
              <option value="archived">Archiviert</option>
            </select>
          </div>
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div><label className={labelClass}>Vorname *</label><Input required value={form.first_name} onChange={(e) => set("first_name", e.target.value)} /></div>
        <div><label className={labelClass}>Nachname *</label><Input required value={form.last_name} onChange={(e) => set("last_name", e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div><label className={labelClass}>E-Mail</label><Input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} /></div>
        <div><label className={labelClass}>Telefon</label><Input value={form.phone} onChange={(e) => set("phone", e.target.value)} /></div>
      </div>
      <div>
        <label className={labelClass}>Anrede (für gendergerechte Profiltexte)</label>
        <select className={selectClass} value={form.anrede} onChange={(e) => set("anrede", e.target.value)}>
          <option value="">Keine Angabe</option>
          <option value="frau">Frau</option>
          <option value="herr">Herr</option>
          <option value="divers">Divers</option>
        </select>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div><label className={labelClass}>Rolle</label><Input value={form.job_title} onChange={(e) => set("job_title", e.target.value)} /></div>
        <div><label className={labelClass}>Qualifikation</label><Input value={form.qualification} onChange={(e) => set("qualification", e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div><label className={labelClass}>PLZ</label><Input value={form.postal_code} onChange={(e) => set("postal_code", e.target.value)} /></div>
        <div><label className={labelClass}>Ort</label><Input value={form.city} onChange={(e) => set("city", e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div><label className={labelClass}>Gehaltswunsch</label><Input value={form.salary_expectation} onChange={(e) => set("salary_expectation", e.target.value)} /></div>
        <div><label className={labelClass}>Kündigungsfrist</label><NoticePeriodField value={form.notice_period} onChange={(value) => set("notice_period", value)} /></div>
      </div>
      <div><label className={labelClass}>Empfohlen von</label><Input placeholder="Name der empfehlenden Person" value={form.referred_by} onChange={(e) => set("referred_by", e.target.value)} /></div>
      <div>
        <label className={labelClass}>Zuständiger Mitarbeiter</label>
        <select className={selectClass} value={ownerUserId} onChange={(e) => set("owner_user_id", e.target.value)}>
          <option value="">Nicht zugewiesen</option>
          {assignableUsers.map((user) => (
            <option key={user.id} value={user.id}>{user.display_name ?? user.email}</option>
          ))}
        </select>
      </div>

      <div className="border-t border-white/10 pt-4">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#92979c]">Quali-Call-Details</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass}>Fachliche Schwerpunkte (Komma-getrennt)</label><Input placeholder="z.B. Jahresabschluss, Umsatzsteuer, M&A" value={form.fachliche_schwerpunkte} onChange={(e) => set("fachliche_schwerpunkte", e.target.value)} /></div>
          <div><label className={labelClass}>Ausbildung / Weiterbildung</label><Input value={form.ausbildung_titel} onChange={(e) => set("ausbildung_titel", e.target.value)} /></div>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass}>Aktuelles Umfeld: Kanzleityp</label><Input value={form.aktuelles_umfeld_kanzleityp} onChange={(e) => set("aktuelles_umfeld_kanzleityp", e.target.value)} /></div>
          <div><label className={labelClass}>Aktuelles Umfeld: Kanzleigröße</label><Input placeholder="z.B. 20-50 Mitarbeitende" value={form.aktuelles_umfeld_kanzleigroesse} onChange={(e) => set("aktuelles_umfeld_kanzleigroesse", e.target.value)} /></div>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label className={labelClass}>Remote-/Teilzeit-Wünsche</label><Input value={form.remote_teilzeit_wuensche} onChange={(e) => set("remote_teilzeit_wuensche", e.target.value)} /></div>
          <div><label className={labelClass}>Passender Kanzleityp</label><Input value={form.passender_kanzleityp} onChange={(e) => set("passender_kanzleityp", e.target.value)} /></div>
        </div>

        <div className="mt-4">
          <div className="mb-2 flex items-center justify-between">
            <label className={labelClass}>Berufliche Stationen</label>
            <Button type="button" size="sm" variant="outline" onClick={() => setStations((current) => [...current, { ...emptyStation }])}><Plus size={13} />Station hinzufügen</Button>
          </div>
          {/* minmax(0, ...) statt bloss fr-Werte: sonst bekommen die Tracks
           * min-width:auto und werden vom Input-Inhalt ueber den Viewport
           * hinaus aufgezogen (gleicher Grid-Overflow-Bug wie bei den
           * Seiten-Grids) - hier bewusst NICHT auf 1 Spalte gestapelt, da
           * das die Loeschen-Zeile pro Station unnoetig hoch machen wuerde. */}
          {stations.map((station, index) => (
            <div key={index} className="mb-2 grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,.6fr)_auto] items-end gap-2">
              <div><Input placeholder="Kanzleityp" value={station.kanzleityp} onChange={(e) => setStation(index, "kanzleityp", e.target.value)} /></div>
              <div><Input placeholder="Kanzleigröße" value={station.kanzleigroesse} onChange={(e) => setStation(index, "kanzleigroesse", e.target.value)} /></div>
              <div><Input type="number" placeholder="Jahre" value={station.dauer_jahre || ""} onChange={(e) => setStation(index, "dauer_jahre", Number(e.target.value))} /></div>
              <Button type="button" size="sm" variant="outline" onClick={() => setStations((current) => current.filter((_, i) => i !== index))}><Trash2 size={13} /></Button>
            </div>
          ))}
        </div>

        <div className="mt-3"><label className={labelClass}>Freitextnotizen</label><textarea className={textareaClass} value={form.freitext_notizen} onChange={(e) => set("freitext_notizen", e.target.value)} /></div>
      </div>

      <div className="rounded-lg border border-[#F0B429]/25 bg-[#F0B429]/5 p-3">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-[#F0B429]">Nur intern — nie in ausgehende Dokumente</p>
        <div>
          <label className={internClass}>Wechselgrund</label>
          <textarea className={textareaClass} value={form.wechselgrund} onChange={(e) => set("wechselgrund", e.target.value)} />
        </div>
        <div className="mt-3">
          <label className={internClass}>No-Gos (Komma-getrennt)</label>
          <Input value={form.no_gos} onChange={(e) => set("no_gos", e.target.value)} />
        </div>
      </div>

      <ErrorBanner message={error} />
      <div className="flex justify-end gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Speichern…" : isEdit ? "Änderungen speichern" : "Kandidat anlegen"}
        </Button>
      </div>
      </form>
    </div>
  );
}

export function CandidateCreateModal({ onCreated }: { onCreated?: (candidate: Candidate) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}><Plus size={15} />Kandidat anlegen</Button>
      {open && (
        <Modal title="Kandidat anlegen" eyebrow="Talent Pool" onClose={() => setOpen(false)}>
          <CandidateCreateForm onDone={(candidate) => { setOpen(false); onCreated?.(candidate); }} />
        </Modal>
      )}
    </>
  );
}

export function CandidateEditModal({
  candidate,
  onUpdated,
}: {
  candidate: Candidate;
  onUpdated?: (candidate: Candidate) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}><Pencil size={13} />Bearbeiten</Button>
      {open && (
        <Modal title="Kandidat bearbeiten" eyebrow="Talent Pool" onClose={() => setOpen(false)}>
          <CandidateCreateForm
            candidate={candidate}
            onDone={(updated) => { setOpen(false); onUpdated?.(updated); }}
          />
        </Modal>
      )}
    </>
  );
}
