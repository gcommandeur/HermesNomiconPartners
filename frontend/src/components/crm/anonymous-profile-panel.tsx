"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Download, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiDownload, apiPatch, apiPost } from "@/lib/api/client";
import { ErrorBanner } from "@/components/crm/error-banner";

interface AnonymousProfilePanelProps {
  candidateId: string;
  initialText: string;
}

export function AnonymousProfilePanel({ candidateId, initialText }: AnonymousProfilePanelProps) {
  const router = useRouter();
  const [text, setText] = useState(initialText);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    setSavedAt(null);
    try {
      const result = await apiPost<{ profile_text: string }>(
        `/candidates/${candidateId}/anonymous-profile`,
        {},
      );
      setText(result.profile_text);
    } catch (exception) {
      setError(
        exception instanceof Error
          ? exception.message
          : "Profil konnte nicht generiert werden.",
      );
    } finally {
      setGenerating(false);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await apiPatch(`/candidates/${candidateId}`, { short_profile: text });
      setSavedAt(new Date());
      router.refresh();
    } catch (exception) {
      setError(
        exception instanceof Error ? exception.message : "Konnte nicht gespeichert werden.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDownload() {
    setDownloading(true);
    setError(null);
    try {
      // The docx endpoint reads short_profile from the DB, not this component's
      // state - without this, downloading right after "Anonymes Profil
      // vorbereiten" (before clicking "Speichern") would silently export the
      // OLD saved text, or fail with "kein anonymes Profil vorhanden" if
      // nothing was ever saved. Always save first so download == what's on screen.
      await apiPatch(`/candidates/${candidateId}`, { short_profile: text });
      setSavedAt(new Date());
      await apiDownload(`/candidates/${candidateId}/anonymous-profile.docx`, `Profil_${candidateId}.docx`);
      router.refresh();
    } catch (exception) {
      setError(
        exception instanceof Error ? exception.message : "Word-Dokument konnte nicht erstellt werden.",
      );
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Card>
      <CardContent>
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h2 className="font-semibold">Anonymes Profil vorbereiten</h2>
            <p className="mt-1 text-xs text-[#7b8187]">
              Vorlagenbasierter, editierbarer Entwurf für CV-Outs und Mailing. Kein automatischer Versand.
            </p>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleGenerate} disabled={generating}>
              <FileText size={14} />
              {generating ? "Wird generiert…" : "Anonymes Profil vorbereiten"}
            </Button>
            <Button size="sm" variant="outline" onClick={handleDownload} disabled={downloading || text.trim() === ""}>
              <Download size={14} />
              {downloading ? "Wird erstellt…" : "Als Word (mit Logo) herunterladen"}
            </Button>
          </div>
        </div>
        <ErrorBanner message={error} className="mt-4" />
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          className="mt-5 min-h-56 w-full rounded-lg border border-white/10 bg-[#0D1B2E] p-4 text-sm leading-7 text-[#F8FAFC] outline-none focus:border-[#1F5FA8]"
        />
        <div className="mt-3 flex items-center justify-end gap-3">
          {savedAt && <span className="text-xs text-[#7b8187]">Gespeichert {savedAt.toLocaleTimeString("de-DE")}</span>}
          <Button variant="dark" size="sm" onClick={handleSave} disabled={saving || text.trim() === ""}>
            {saving ? "Speichert…" : "Im Kandidatenprofil speichern"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
