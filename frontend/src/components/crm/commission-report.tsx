"use client";

// NOMICON: Provisionsmodell - Abschnitt der Geschäftsführer-Ansicht (NUR Admins): Quartalsbericht je
// Mitarbeiter mit Provision, Kosten, Marge, Break-even, Ampel und Beförderungshinweis; Rangzuordnung
// und Einstellungen des Modells.
import { useState } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Plus, Settings2, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { ErrorBanner } from "@/components/crm/error-banner";
import { ErrorState } from "@/components/crm/error-state";
import { invalidateCommission, useCommissionConfig, useCommissionReport, useCommissionUsers } from "@/lib/api/commission-hooks";
import {
  currentQuarter,
  eur,
  saveCommissionConfig,
  setCommissionUserRank,
  shiftQuarter,
  type CommissionConfig,
  type CommissionConfigInput,
  type CommissionRow,
} from "@/lib/api/commission";
import { formatDate } from "@/lib/utils";
import { formatPercent } from "@/lib/format"; // NOMICON
import { moveItem, rankKeyFromLabel } from "@/lib/commission-ui"; // NOMICON

const TRAFFIC_TONE = { green: "green", yellow: "amber", red: "red" } as const;
const TRAFFIC_LABEL = { green: "Ziel erreicht", yellow: "Über Break-even", red: "Unter Break-even" } as const;
const labelClass = "mb-1 block text-xs text-brand-muted";
const selectClass = "h-9 rounded-md border border-white/10 bg-brand-surface px-2 text-sm text-brand-text outline-none focus:border-brand-accent";

function percent(value: string | null): string {
  return value === null ? "–" : formatPercent(value);
}

export function CommissionReport() {
  const initial = currentQuarter();
  const [period, setPeriod] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data, error: loadError, isLoading, mutate } = useCommissionReport(period.year, period.quarter);
  const { data: configData } = useCommissionConfig();
  const { data: usersData } = useCommissionUsers();
  const ranks = configData?.data.ranks ?? [];

  async function setRank(userId: string, rankKey: string | null) {
    setError(null);
    try {
      await setCommissionUserRank(userId, rankKey);
      await invalidateCommission();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Rang konnte nicht gesetzt werden.");
    }
  }

  const report = data?.data;
  const unranked = (usersData?.data ?? []).filter((user) => user.rank_key === null);

  return (
    <section className="mt-10" aria-labelledby="commission-title">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="commission-title" className="text-lg font-semibold tracking-[-.02em]">Provisionsmodell</h2>
          <p className="text-xs text-brand-muted">Nur für Admins sichtbar · Gehalts- und Margendaten</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1" role="group" aria-label="Quartal wählen">
            <Button size="icon" variant="outline" aria-label="Voriges Quartal" onClick={() => setPeriod((p) => shiftQuarter(p.year, p.quarter, -1))}><ChevronLeft size={16} /></Button>
            <span className="min-w-[5.5rem] text-center text-sm font-medium">Q{period.quarter} {period.year}</span>
            <Button size="icon" variant="outline" aria-label="Nächstes Quartal" onClick={() => setPeriod((p) => shiftQuarter(p.year, p.quarter, 1))}><ChevronRight size={16} /></Button>
          </div>
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Settings2 size={14} />Modell einstellen</Button>
        </div>
      </div>

      <ErrorBanner message={error} className="mb-3" />

      {loadError ? (
        <ErrorState onRetry={() => void mutate()} />
      ) : isLoading || !report ? (
        <div className="h-32 animate-pulse rounded-xl bg-brand-surface" aria-busy="true" aria-label="Wird geladen" />
      ) : (
        <>
          <p className="mb-3 text-xs text-brand-muted">
            {formatDate(report.period_start)} – {formatDate(report.period_end)} · Umsatz: {report.revenue_basis.placement_fees === "paid" ? "bezahlte" : "gestellte"} Vermittlungshonorare
            {report.revenue_basis.include_staffing ? ` + ${report.revenue_basis.staffing === "paid" ? "bezahlte" : "gestellte"} Überlassungsrechnungen` : ""} · Ziel-Marge {percent(report.target_margin)}
          </p>
          {report.rows.length === 0 ? (
            <Card><CardContent className="py-10 text-center text-sm text-brand-muted">Noch keinem Mitarbeiter ist ein Rang zugeordnet. Unten Rang zuweisen.</CardContent></Card>
          ) : (
            <Card>
              <CardContent className="overflow-x-auto p-0">
                <table className="w-full min-w-[64rem] text-left text-xs">
                  <thead>
                    <tr className="border-b border-white/10 text-[9.5px] uppercase tracking-wider text-brand-muted">
                      <th className="px-4 py-3">Mitarbeiter:in</th>
                      <th className="px-3 py-3">Rang</th>
                      <th className="px-3 py-3 text-right">Umsatz</th>
                      <th className="px-3 py-3 text-right">Provision</th>
                      <th className="px-3 py-3 text-right">Bonus</th>
                      <th className="px-3 py-3 text-right">Brutto</th>
                      <th className="px-3 py-3 text-right">Kosten</th>
                      <th className="px-3 py-3 text-right">Marge</th>
                      <th className="px-3 py-3 text-right">Break-even</th>
                      <th className="px-3 py-3">Ampel</th>
                      <th className="px-3 py-3">Beförderung</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.rows.map((row) => <Row key={row.user_id} row={row} ranks={ranks} onRank={setRank} />)}
                  </tbody>
                  <tfoot>
                    <tr className="border-t border-white/10 font-semibold">
                      <td className="px-4 py-3" colSpan={2}>Gesamt</td>
                      <td className="px-3 py-3 text-right">{eur(report.totals.revenue)}</td>
                      <td className="px-3 py-3 text-right">{eur(report.totals.commission)}</td>
                      <td className="px-3 py-3" />
                      <td className="px-3 py-3" />
                      <td className="px-3 py-3 text-right">{eur(report.totals.employer_cost)}</td>
                      <td className="px-3 py-3 text-right">{eur(report.totals.margin)} <span className="font-normal text-brand-muted">({percent(report.totals.margin_percent)})</span></td>
                      <td className="px-3 py-3" />
                      <td className="px-3 py-3"><Badge tone={TRAFFIC_TONE[report.totals.traffic]}>{TRAFFIC_LABEL[report.totals.traffic]}</Badge></td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </CardContent>
            </Card>
          )}

          {report.unassigned.length > 0 && (
            <p role="status" className="mt-3 rounded-lg border border-brand-warning/30 bg-brand-warning/10 p-3 text-xs text-brand-warning">
              Umsatz ohne Rang: {report.unassigned.map((u) => `${u.display_name} (${eur(u.revenue)})`).join(", ")} – bitte unten einen Rang zuweisen.
            </p>
          )}
          {unranked.length > 0 && (
            <div className="mt-4">
              <h3 className="mb-2 text-sm font-semibold">Mitarbeiter ohne Rang</h3>
              <ul className="space-y-2">
                {unranked.map((user) => (
                  <li key={user.user_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 p-2.5 text-sm">
                    <span>{user.display_name}</span>
                    <select aria-label={`Rang für ${user.display_name}`} className={selectClass} value="" onChange={(e) => e.target.value && void setRank(user.user_id, e.target.value)}>
                      <option value="">Rang zuweisen…</option>
                      {ranks.map((rank) => <option key={rank.key} value={rank.key}>{rank.label}</option>)}
                    </select>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {report.notice && <p className="mt-4 text-[10.45px] leading-relaxed text-brand-dim">{report.notice}</p>}
        </>
      )}
      {editing && configData && <ConfigModal config={configData.data} onClose={() => setEditing(false)} />}
    </section>
  );
}

function Row({ row, ranks, onRank }: { row: CommissionRow; ranks: { key: string; label: string }[]; onRank: (userId: string, rankKey: string | null) => Promise<void> }) {
  return (
    <tr className="border-b border-white/5 align-top">
      <td className="px-4 py-3 font-semibold text-brand-text">{row.display_name}</td>
      <td className="px-3 py-3">
        <select aria-label={`Rang für ${row.display_name}`} className={selectClass} value={row.rank_key} onChange={(e) => void onRank(row.user_id, e.target.value || null)}>
          {ranks.map((rank) => <option key={rank.key} value={rank.key}>{rank.label}</option>)}
          <option value="">Rang entfernen</option>
        </select>
      </td>
      <td className="px-3 py-3 text-right">
        {eur(row.revenue)}
        <span className="block text-[10.45px] text-brand-muted">Vermittlung {eur(row.revenue_fees)} · Überlassung {eur(row.revenue_staffing)}</span>
      </td>
      <td className="px-3 py-3 text-right">{eur(row.commission)}<span className="block text-[10.45px] text-brand-muted">Fix {eur(row.fixed_pay)}</span></td>
      <td className="px-3 py-3 text-right">{eur(row.bonus)}<span className="block text-[10.45px] text-brand-muted">{row.placement_deals + row.staffing_deals} Deal(s)</span></td>
      <td className="px-3 py-3 text-right">{eur(row.gross)}</td>
      <td className="px-3 py-3 text-right">{eur(row.employer_cost)}</td>
      <td className="px-3 py-3 text-right">{eur(row.margin)}<span className="block text-[10.45px] text-brand-muted">{percent(row.margin_percent)}</span></td>
      <td className="px-3 py-3 text-right">{eur(row.break_even_revenue)}<span className="block text-[10.45px] text-brand-muted">Ziel {eur(row.target_revenue)}</span></td>
      <td className="px-3 py-3"><Badge tone={TRAFFIC_TONE[row.traffic]}>{TRAFFIC_LABEL[row.traffic]}</Badge></td>
      <td className="px-3 py-3">
        {row.promotion_to_key ? (
          <div className="space-y-1">
            <span className="block text-brand-success-text">→ {row.promotion_to_label}</span>
            <Button size="sm" variant="outline" onClick={() => void onRank(row.user_id, row.promotion_to_key)}>Befördern</Button>
          </div>
        ) : row.promotion_hurdle ? (
          <span className="text-brand-muted">ab {eur(row.promotion_hurdle)}</span>
        ) : (
          <span className="text-brand-muted">höchster Rang</span>
        )}
      </td>
    </tr>
  );
}

// --- Einstellungen -----------------------------------------------------------------------------

type RankForm = Record<"key" | "label" | "fixed_yearly" | "rate1" | "threshold1" | "rate2" | "threshold2" | "rate3", string>;

const GENERAL_FIELDS: { key: keyof CommissionConfig["general"]; label: string }[] = [
  { key: "commission_free_base", label: "Umsatz ohne Provision je Quartal (€)" },
  { key: "employer_factor", label: "Arbeitgeber-Faktor" },
  { key: "extra_cost_monthly", label: "Zusatzkosten je Monat und Kopf (€)" },
  { key: "fee_rate_on_target_salary", label: "Honorarsatz auf Zielgehalt (%) – nur hinterlegt" },
  { key: "min_fee", label: "Mindesthonorar (€) – nur hinterlegt" },
  { key: "target_margin", label: "Ziel-Marge (%)" },
  { key: "placement_bonus", label: "Vermittlungsbonus je Deal (€)" },
  { key: "staffing_bonus", label: "Überlassungsbonus je Deal (€)" },
];

const RANK_COLUMNS: { key: keyof RankForm; label: string; wide?: boolean }[] = [
  { key: "label", label: "Rang", wide: true },
  { key: "fixed_yearly", label: "Fix €/Jahr" },
  { key: "rate1", label: "Satz 1 %" },
  { key: "threshold1", label: "bis (€)" },
  { key: "rate2", label: "Satz 2 %" },
  { key: "threshold2", label: "bis (€) = Beförderung" },
  { key: "rate3", label: "Satz 3 %" },
];

function ConfigModal({ config, onClose }: { config: CommissionConfig; onClose: () => void }) {
  const [general, setGeneral] = useState(() => Object.fromEntries(Object.entries(config.general).map(([k, v]) => [k, String(v)])) as Record<string, string>);
  const [ranks, setRanks] = useState<RankForm[]>(() =>
    config.ranks.map((r) => ({
      key: r.key, label: r.label, fixed_yearly: String(r.fixed_yearly), rate1: String(r.rate1), threshold1: String(r.threshold1),
      rate2: String(r.rate2), threshold2: String(r.threshold2), rate3: String(r.rate3),
    })),
  );
  const [basis, setBasis] = useState(config.revenue_basis);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setRankField(index: number, field: keyof RankForm, value: string) {
    setRanks((current) => current.map((rank, i) => (i === index ? { ...rank, [field]: value } : rank)));
  }

  function addRank() {
    setRanks((current) => {
      const last = current[current.length - 1];
      const label = `Neue Stufe ${current.length + 1}`;
      const key = rankKeyFromLabel(label, current.map((r) => r.key));
      return [...current, { ...(last ?? { fixed_yearly: "0", rate1: "0", threshold1: "0", rate2: "0", threshold2: "0", rate3: "0" }), key, label }];
    });
  }

  function removeRank(index: number) {
    setRanks((current) => (current.length > 1 ? current.filter((_, i) => i !== index) : current));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const num = (value: string) => value.replace(",", ".");
      const payload: CommissionConfigInput = {
        general: {
          commission_free_base: num(general.commission_free_base), employer_factor: num(general.employer_factor),
          extra_cost_monthly: num(general.extra_cost_monthly), fee_rate_on_target_salary: num(general.fee_rate_on_target_salary),
          min_fee: num(general.min_fee), target_margin: num(general.target_margin),
          placement_bonus: num(general.placement_bonus), staffing_bonus: num(general.staffing_bonus),
        },
        ranks: ranks.map((r) => ({
          key: r.key, label: r.label, fixed_yearly: num(r.fixed_yearly), rate1: num(r.rate1), threshold1: num(r.threshold1),
          rate2: num(r.rate2), threshold2: num(r.threshold2), rate3: num(r.rate3),
        })),
        revenue_basis: basis,
      };
      await saveCommissionConfig(payload);
      await invalidateCommission();
      onClose();
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Speichern fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Provisionsmodell einstellen" eyebrow="Nur Admins" onClose={onClose} maxWidth="max-w-4xl">
      <form className="space-y-6" onSubmit={submit}>
        <section>
          <h3 className="mb-2 text-sm font-semibold">Allgemein</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {GENERAL_FIELDS.map((field) => (
              <div key={field.key}>
                <label className={labelClass} htmlFor={`cg-${field.key}`}>{field.label}</label>
                <Input id={`cg-${field.key}`} inputMode="decimal" required value={general[field.key] ?? ""} onChange={(e) => setGeneral((c) => ({ ...c, [field.key]: e.target.value }))} />
              </div>
            ))}
          </div>
        </section>
        <section>
          <h3 className="mb-1 text-sm font-semibold">Umsatzbasis</h3>
          <p className="mb-2 text-xs text-brand-muted">Was als Umsatz eines Mitarbeiters zählt – laut Karriereplan nur bezahlte Vermittlungshonorare und bezahlte Überlassungsrechnungen, jeweils im Quartal des Zahldatums. Der Bonus zählt immer erst mit der Zahlung.</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className={labelClass} htmlFor="cb-fees">Vermittlungshonorare</label>
              <select id="cb-fees" className={`${selectClass} w-full`} value={basis.placement_fees} onChange={(e) => setBasis({ ...basis, placement_fees: e.target.value as "paid" | "issued" })}>
                <option value="paid">nur bezahlte</option><option value="issued">ab Rechnung gestellt</option>
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="cb-inc">Überlassung</label>
              <select id="cb-inc" className={`${selectClass} w-full`} value={basis.include_staffing ? "yes" : "no"} onChange={(e) => setBasis({ ...basis, include_staffing: e.target.value === "yes" })}>
                <option value="yes">mitzählen</option><option value="no">nicht mitzählen</option>
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="cb-st">Überlassungsrechnungen</label>
              <select id="cb-st" className={`${selectClass} w-full`} disabled={!basis.include_staffing} value={basis.staffing} onChange={(e) => setBasis({ ...basis, staffing: e.target.value as "issued" | "paid" })}>
                <option value="issued">ab gestellt</option><option value="paid">nur bezahlte</option>
              </select>
            </div>
          </div>
        </section>
        <section>
          <h3 className="mb-1 text-sm font-semibold">Ränge (aufsteigend)</h3>
          <p className="mb-2 text-xs text-brand-muted">Gestaffelt je Quartal: Satz 1 bis zur ersten Schwelle, Satz 2 bis zur zweiten (zugleich Beförderungshürde), darüber Satz 3. Die ersten Euro bis zur Freigrenze bringen keine Provision.</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-xs">
              <thead><tr className="text-left text-[9.5px] uppercase tracking-wider text-brand-muted">{RANK_COLUMNS.map((c) => <th key={c.key} className="pb-2 pr-2 font-medium">{c.label}</th>)}<th className="pb-2 font-medium"><span className="sr-only">Reihenfolge und Entfernen</span></th></tr></thead>
              <tbody>
                {ranks.map((rank, index) => (
                  <tr key={rank.key}>
                    {RANK_COLUMNS.map((column) => (
                      <td key={column.key} className="pr-2 pb-2">
                        <Input aria-label={`${rank.label}: ${column.label}`} className={column.wide ? "h-9 min-w-[11rem]" : "h-9"} required inputMode={column.key === "label" ? "text" : "decimal"} value={rank[column.key]} onChange={(e) => setRankField(index, column.key, e.target.value)} />
                      </td>
                    ))}
                    <td className="whitespace-nowrap pb-2">
                      <Button type="button" size="icon" variant="outline" aria-label={`${rank.label} nach oben`} disabled={index === 0} onClick={() => setRanks((c) => moveItem(c, index, -1))}><ArrowUp size={14} /></Button>{" "}
                      <Button type="button" size="icon" variant="outline" aria-label={`${rank.label} nach unten`} disabled={index === ranks.length - 1} onClick={() => setRanks((c) => moveItem(c, index, 1))}><ArrowDown size={14} /></Button>{" "}
                      <Button type="button" size="icon" variant="outline" aria-label={`${rank.label} entfernen`} disabled={ranks.length <= 1} onClick={() => removeRank(index)}><Trash2 size={14} /></Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button type="button" size="sm" variant="outline" className="mt-2" onClick={addRank}><Plus size={14} />Stufe hinzufügen</Button>
          <p className="mt-2 text-xs text-brand-muted">Die Reihenfolge ist die Karriereleiter (unten = höchste Stufe, dort gibt es keine Beförderung). Umbenennen ändert keine Zuweisungen; wird eine Stufe entfernt, erscheinen ihre Mitarbeiter:innen unter „ohne Rang“ und bekommen einen neuen Rang vom Admin.</p>
        </section>
        <ErrorBanner message={error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Abbrechen</Button>
          <Button type="submit" disabled={busy}>{busy ? "Speichern…" : "Speichern"}</Button>
        </div>
      </form>
    </Modal>
  );
}
