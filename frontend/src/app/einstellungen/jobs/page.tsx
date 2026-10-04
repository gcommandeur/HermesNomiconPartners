"use client";

import { useCallback, useEffect, useState } from "react";
import { ShieldOff } from "lucide-react";
import { PageHeader } from "@/components/crm/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/lib/api/hooks";
import { getBackgroundJobs, retryBackgroundJob } from "@/lib/api/queries";
import type { BackgroundJob } from "@/lib/api/types";

const KIND_LABELS: Record<string, string> = {
  security_alert: "Sicherheitswarnung (Mail)",
  "sourcing.team_pages": "Sourcing: Team-Seiten scannen",
  "sourcing.areas": "Sourcing: Verzeichnis-Umkreissuche",
  "cv.scan": "CV-Scan (gescanntes PDF)",
  "webhook.deliver": "Webhook-Zustellung",
};

const STATUS_LABELS: Record<BackgroundJob["status"], string> = {
  queued: "wartet",
  running: "läuft",
  done: "erledigt",
  failed: "fehlgeschlagen",
};

const FILTERS: { value: string; label: string }[] = [
  { value: "failed", label: "Fehlgeschlagen" },
  { value: "queued", label: "Wartend" },
  { value: "running", label: "Laufend" },
  { value: "done", label: "Erledigt" },
  { value: "", label: "Alle" },
];

export default function HintergrundjobsPage() {
  const { data: meData, isLoading: meLoading } = useCurrentUser();
  const isAdmin = meData?.data.is_admin ?? false;
  const [filter, setFilter] = useState("failed");
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const result = await getBackgroundJobs(filter || undefined);
    setJobs(result.data);
  }, [filter]);

  useEffect(() => {
    if (!isAdmin) return;
    void load();
  }, [isAdmin, load]);

  async function handleRetry(jobId: string) {
    setMessage(null);
    try {
      await retryBackgroundJob(jobId);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Job konnte nicht neu gestartet werden.");
    }
  }

  if (meLoading) {
    return <div className="h-16 animate-pulse rounded-lg bg-brand-surface" />;
  }

  if (!isAdmin) {
    return (
      <>
        <PageHeader eyebrow="Einstellungen" title="Hintergrundjobs" />
        <Card>
          <CardContent className="flex items-center gap-3 text-sm text-brand-muted">
            <ShieldOff size={18} /> Nur für Admins zugänglich.
          </CardContent>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow="Einstellungen" title="Hintergrundjobs" />
      <p className="mb-5 max-w-3xl text-sm text-brand-muted">
        Aufgaben, die im Hintergrund laufen (Sourcing-Läufe, CV-Scans, Sicherheitswarnungen, Webhooks). Fehler werden
        automatisch mehrfach wiederholt; danach erscheint der Job hier als fehlgeschlagen und kann neu gestartet werden.
      </p>
      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((item) => (
          <Button
            key={item.value}
            size="sm"
            variant={filter === item.value ? "default" : "outline"}
            onClick={() => setFilter(item.value)}
          >
            {item.label}
          </Button>
        ))}
      </div>
      {message && <p className="mb-3 text-sm text-red-300">{message}</p>}
      <div className="space-y-3">
        {jobs.length === 0 && <p className="text-sm text-brand-muted">Keine Jobs in dieser Ansicht.</p>}
        {jobs.map((job) => (
          <Card key={job.id}>
            <CardContent className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-medium">{KIND_LABELS[job.kind] ?? job.kind}</p>
                <p className="text-xs text-brand-muted">
                  {STATUS_LABELS[job.status]} · Versuch {job.attempts}/{job.max_attempts} · angelegt{" "}
                  {new Date(job.created_at).toLocaleString("de-DE")}
                </p>
                {job.last_error && <p className="mt-1 break-words text-xs text-red-300">{job.last_error}</p>}
              </div>
              {job.status === "failed" && (
                <Button size="sm" variant="outline" onClick={() => void handleRetry(job.id)}>
                  Neu starten
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
