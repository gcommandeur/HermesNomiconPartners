"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Pencil, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { apiPatch } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";
import type { ClientCompany, HonorarStufe } from "@/lib/api/types";

const labelClass = "mb-1 block text-xs text-[#777d83]";
const selectClass = "h-10 w-full rounded-md border border-white/10 bg-[#0D1B2E] px-3 text-sm text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

const honorarStufeOptions: { value: HonorarStufe; label: string }[] = [
  { value: "standard", label: "Standard (27 %) — größere/etablierte Kanzleien" },
  { value: "nachlass_1", label: "Nachlass 1 (25 %) — kleinere Kanzlei, begrenztes Budget" },
  { value: "nachlass_2", label: "Nachlass 2 (23 %) — sehr kleine/Einzelkanzlei" },
  { value: "individuell", label: "Individuell" },
];

const honorarStufeLabel = (value?: HonorarStufe) =>
  honorarStufeOptions.find((option) => option.value === value)?.label ?? "Standard";

export function ClientHonorarEditor({ client }: { client: ClientCompany }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    fee_percentage: String(client.fee_percentage ?? 27),
    honorar_stufe: (client.honorar_stufe ?? "standard") as HonorarStufe,
    nachlass_begruendung: client.nachlass_begruendung ?? "",
    agb_version: client.agb_version ?? "",
  });

  function reset() {
    setForm({
      fee_percentage: String(client.fee_percentage ?? 27),
      honorar_stufe: (client.honorar_stufe ?? "standard") as HonorarStufe,
      nachlass_begruendung: client.nachlass_begruendung ?? "",
      agb_version: client.agb_version ?? "",
    });
    setError(null);
  }

  async function handleSave() {
    setBusy(true);
    setError(null);
    try {
      await apiPatch(`/clients/${client.id}`, {
        fee_percentage: form.fee_percentage,
        honorar_stufe: form.honorar_stufe,
        nachlass_begruendung: form.nachlass_begruendung.trim() === "" ? null : form.nachlass_begruendung,
        agb_version: form.agb_version.trim() === "" ? null : form.agb_version,
      });
      setEditing(false);
      router.refresh();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Konnte nicht gespeichert werden.");
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <Card>
        <CardContent>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs text-[#777d83]">Honorarsatz</p>
              <p className="mt-2 font-medium">{client.fee_percentage ?? 27} %</p>
            </div>
            <Button size="sm" variant="outline" onClick={() => { reset(); setEditing(true); }}><Pencil size={13} />Bearbeiten</Button>
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div><p className="text-xs text-[#777d83]">Honorar-Stufe</p><p className="mt-2 text-sm">{honorarStufeLabel(client.honorar_stufe)}</p></div>
            <div><p className="text-xs text-[#777d83]">AGB-Version</p><p className="mt-2 text-sm">{client.agb_version ?? "—"}</p></div>
          </div>
          {client.nachlass_begruendung && (
            <div className="mt-4"><p className="text-xs text-[#777d83]">Nachlass-Begründung</p><p className="mt-2 text-sm text-[#CBD5E1]">{client.nachlass_begruendung}</p></div>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div><label className={labelClass}>Honorarsatz (%)</label><Input type="number" step="0.01" value={form.fee_percentage} onChange={(e) => setForm((current) => ({ ...current, fee_percentage: e.target.value }))} /></div>
          <div>
            <label className={labelClass}>Honorar-Stufe</label>
            <select className={selectClass} value={form.honorar_stufe} onChange={(e) => setForm((current) => ({ ...current, honorar_stufe: e.target.value as HonorarStufe }))}>
              {honorarStufeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div><label className={labelClass}>Nachlass-Begründung</label><Input placeholder="z.B. kleine Kanzlei, begrenztes Budget" value={form.nachlass_begruendung} onChange={(e) => setForm((current) => ({ ...current, nachlass_begruendung: e.target.value }))} /></div>
          <div><label className={labelClass}>AGB-Version</label><Input value={form.agb_version} onChange={(e) => setForm((current) => ({ ...current, agb_version: e.target.value }))} /></div>
        </div>
        <ErrorBanner message={error} className="mt-3" />
        <div className="mt-4 flex justify-end gap-2">
          <Button size="sm" variant="outline" onClick={() => { reset(); setEditing(false); }}><X size={13} />Abbrechen</Button>
          <Button size="sm" disabled={busy} onClick={handleSave}><Save size={13} />{busy ? "Speichern…" : "Speichern"}</Button>
        </div>
      </CardContent>
    </Card>
  );
}
