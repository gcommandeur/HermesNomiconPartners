"use client";

import { useEffect, useState } from "react";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { ErrorState } from "@/components/crm/error-state";
import { ErrorBanner } from "@/components/crm/error-banner";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiPut } from "@/lib/api/client";
import { useAppSettingsCache, useCurrentUser, useKpiPointRulesCache } from "@/lib/api/hooks";
import { PITCH_LABEL, STAGE_LABELS } from "@/lib/stage-labels";
import type { AppSettings, KpiPointRule } from "@/lib/api/types";

// Deckungsgleich mit STAGE_KEYS in backend/src/cc_crm/services/
// kpi_scoring.py - dort die eigentliche Quelle der Wahrheit fuer die
// Reihenfolge, hier nur zur Anzeige. "pitch" ist keine SubmissionStatus-
// Stufe (siehe PITCH_LABEL-Docstring in stage-labels.ts), daher nicht in
// STAGE_LABELS enthalten und separat gelabelt.
const STAGE_ORDER_WITH_PITCH: { key: string; label: string }[] = [
  { key: "pitch", label: PITCH_LABEL },
  { key: "qualification_call", label: STAGE_LABELS.qualification_call },
  { key: "cv_in", label: STAGE_LABELS.cv_in },
  { key: "cv_out", label: STAGE_LABELS.cv_out },
  { key: "interview", label: STAGE_LABELS.interview },
  { key: "offer", label: STAGE_LABELS.offer },
  { key: "placement", label: STAGE_LABELS.placement },
];

const METRIC_OPTIONS = [
  { value: "points", label: "Punkte (gesamt)" },
  ...STAGE_ORDER_WITH_PITCH.map(({ key, label }) => ({ value: key, label })),
];

const selectClass = "h-10 w-full rounded-md border border-white/10 bg-brand-surface px-3 text-sm text-brand-text outline-none focus:border-brand-accent";
const labelClass = "mb-1 block text-xs text-brand-muted";

function pointsFromRules(rules: KpiPointRule[]): Record<string, number> {
  return Object.fromEntries(rules.map((rule) => [rule.stage, rule.points]));
}

export default function KpiPunktePage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;

  const { data: rulesData, isLoading: rulesLoading, error: rulesError, mutate: retryRules } =
    useKpiPointRulesCache(isAdmin);
  const { data: settingsData, isLoading: settingsLoading, error: settingsError, mutate: retrySettings } =
    useAppSettingsCache(isAdmin);

  const [points, setPoints] = useState<Record<string, number>>({});
  const [settings, setSettings] = useState<AppSettings>({
    kpi_ranking_metric: "points",
    kpi_ranking_period: "week",
  });
  const [rulesBusy, setRulesBusy] = useState(false);
  const [rulesSaved, setRulesSaved] = useState(false);
  const [rulesSaveError, setRulesSaveError] = useState<string | null>(null);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [settingsSaveError, setSettingsSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (rulesData?.data) setPoints(pointsFromRules(rulesData.data));
  }, [rulesData]);

  useEffect(() => {
    if (settingsData?.data) setSettings(settingsData.data);
  }, [settingsData]);

  if (meLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-14 animate-pulse rounded-lg bg-brand-surface" />
        ))}
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Hermes" title="KPI-Punkte" />
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ShieldOff size={28} className="text-brand-muted" />
            <p className="text-sm font-semibold text-brand-text">Nur für Admins zugänglich</p>
            <p className="max-w-sm text-xs text-brand-muted">
              Das Punkte-System steuert die Geschäftsführer-Ansicht und das Live-Ranking für alle
              Nutzer. Wende dich an einen Admin, falls du Zugriff benötigst.
            </p>
          </CardContent>
        </Card>
      </>
    );
  }

  if (rulesError || settingsError) {
    return <ErrorState onRetry={() => { void retryRules(); void retrySettings(); }} />;
  }

  async function handleSaveRules() {
    setRulesBusy(true);
    setRulesSaveError(null);
    setRulesSaved(false);
    try {
      await apiPut("/admin/kpi-point-rules", { rules: points });
      await retryRules();
      setRulesSaved(true);
      setTimeout(() => setRulesSaved(false), 2000);
    } catch (exception) {
      setRulesSaveError(
        exception instanceof Error ? exception.message : "Punkte-Regeln konnten nicht gespeichert werden.",
      );
    } finally {
      setRulesBusy(false);
    }
  }

  async function handleSaveSettings() {
    setSettingsBusy(true);
    setSettingsSaveError(null);
    setSettingsSaved(false);
    try {
      await apiPut("/admin/app-settings", settings);
      await retrySettings();
      setSettingsSaved(true);
      setTimeout(() => setSettingsSaved(false), 2000);
    } catch (exception) {
      setSettingsSaveError(
        exception instanceof Error ? exception.message : "Einstellungen konnten nicht gespeichert werden.",
      );
    } finally {
      setSettingsBusy(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Hermes" title="KPI-Punkte" />
      <div className="space-y-5">
        <Card>
          <CardHeader>
            <div>
              <h2 className="font-semibold">Punkte je Pipeline-Stufe</h2>
              <p className="mt-1 text-xs text-brand-muted">
                Steuert die Gesamt-Punktzahl in der Geschäftsführer-Ansicht und im Live-Ranking
                (Metrik &quot;Punkte&quot;). Werte sind noch nicht definiert (alle auf 0) - hier
                eintragen.
              </p>
            </div>
          </CardHeader>
          <CardContent>
            {rulesLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 7 }).map((_, index) => (
                  <div key={index} className="h-10 animate-pulse rounded-lg bg-brand-surface" />
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                {STAGE_ORDER_WITH_PITCH.map(({ key, label }) => (
                  <div key={key} className="flex items-center justify-between gap-3">
                    <label className="text-sm text-brand-platinum">{label}</label>
                    <Input
                      type="number"
                      min={0}
                      className="w-28"
                      value={points[key] ?? 0}
                      onChange={(e) =>
                        setPoints((current) => ({ ...current, [key]: Number(e.target.value) || 0 }))
                      }
                    />
                  </div>
                ))}
              </div>
            )}
            <ErrorBanner message={rulesSaveError} className="mt-3" />
            <div className="mt-4 flex items-center gap-3">
              <Button size="sm" disabled={rulesBusy || rulesLoading} onClick={handleSaveRules}>
                {rulesBusy ? "Speichern…" : "Punkte-Regeln speichern"}
              </Button>
              {rulesSaved && <span className="text-xs text-brand-success-text">Gespeichert.</span>}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <h2 className="font-semibold">Live-Ranking-Voreinstellung</h2>
              <p className="mt-1 text-xs text-brand-muted">
                Standard-Metrik und -Zeitraum für das Ranking-Widget auf dem Cockpit - jede:r
                Nutzer:in kann Tag/Woche im Widget selbst umschalten, die Metrik ist global.
              </p>
            </div>
          </CardHeader>
          <CardContent>
            {settingsLoading ? (
              <div className="h-20 animate-pulse rounded-lg bg-brand-surface" />
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className={labelClass}>Metrik</label>
                  <select
                    className={selectClass}
                    value={settings.kpi_ranking_metric}
                    onChange={(e) =>
                      setSettings((current) => ({ ...current, kpi_ranking_metric: e.target.value }))
                    }
                  >
                    {METRIC_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className={labelClass}>Standard-Zeitraum</label>
                  <select
                    className={selectClass}
                    value={settings.kpi_ranking_period}
                    onChange={(e) =>
                      setSettings((current) => ({
                        ...current,
                        kpi_ranking_period: e.target.value as "day" | "week",
                      }))
                    }
                  >
                    <option value="day">Tag</option>
                    <option value="week">Woche</option>
                  </select>
                </div>
              </div>
            )}
            <ErrorBanner message={settingsSaveError} className="mt-3" />
            <div className="mt-4 flex items-center gap-3">
              <Button size="sm" disabled={settingsBusy || settingsLoading} onClick={handleSaveSettings}>
                {settingsBusy ? "Speichern…" : "Voreinstellung speichern"}
              </Button>
              {settingsSaved && <span className="text-xs text-brand-success-text">Gespeichert.</span>}
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
