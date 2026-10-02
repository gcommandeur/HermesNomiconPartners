"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/crm/error-banner";
import { useAssignableUsersCache, useCurrentUser } from "@/lib/api/hooks";
import { createSubmissionShare, deleteSubmissionShare, getSubmissionShares } from "@/lib/api/queries";
import type { SubmissionShare } from "@/lib/api/types";

const selectClass = "h-8 rounded-md border border-white/10 bg-[#0D1B2E] px-2 text-xs text-[#F8FAFC] outline-none focus:border-[#1F5FA8]";

/** "Geteilt mit": gezielte Freigabe EINES Prozesses an Kollegen (Vertretung,
 * Vier-Augen-Pruefung) - voller Zugriff, kein Berechtigungslevel. Teilen und
 * Entziehen duerfen Eigentuemer, Teamleiter und Admins (das Backend prueft
 * endgueltig und antwortet sonst mit 403); ein Empfaenger sieht nur seine
 * eigene Freigabe als entfernbar ("zurueckgeben"). */
export function SubmissionSharesPanel({
  submissionId,
  ownerUserId,
}: {
  submissionId: string;
  ownerUserId: string | null | undefined;
}) {
  const { data: meData } = useCurrentUser();
  const me = meData?.data;
  const { data: usersData } = useAssignableUsersCache();
  const [shares, setShares] = useState<SubmissionShare[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSubmissionShares(submissionId)
      .then((result) => {
        if (!cancelled) setShares(result.data);
      })
      .catch(() => {
        // Ohne Zugriff/offline bleibt der Bereich einfach leer.
      });
    return () => {
      cancelled = true;
    };
  }, [submissionId]);

  const canManage = !!me && (me.is_admin || me.role === "team_lead" || me.id === ownerUserId);
  const candidates = (usersData?.data ?? []).filter(
    (user) =>
      user.id !== me?.id &&
      user.id !== ownerUserId &&
      !shares.some((share) => share.shared_with_user_id === user.id),
  );

  async function handleAdd() {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      const created = await createSubmissionShare(submissionId, selected);
      setShares((list) => (list.some((item) => item.id === created.id) ? list : [...list, created]));
      setSelected("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Prozess konnte nicht geteilt werden.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(share: SubmissionShare) {
    setBusy(true);
    setMessage(null);
    try {
      await deleteSubmissionShare(submissionId, share.id);
      setShares((list) => list.filter((item) => item.id !== share.id));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Freigabe konnte nicht entfernt werden.");
    } finally {
      setBusy(false);
    }
  }

  if (!canManage && shares.length === 0) return null;

  return (
    <div className="space-y-2 rounded-lg border border-white/10 bg-[#0D1B2E]/60 p-3">
      <p className="text-xs text-[#94A3B8]">Geteilt mit</p>
      <div className="flex flex-wrap items-center gap-2">
        {shares.length === 0 && <span className="text-xs text-[#64748B]">Noch mit niemandem geteilt.</span>}
        {shares.map((share) => {
          const removable = canManage || share.shared_with_user_id === me?.id;
          return (
            <span
              key={share.id}
              className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 py-0.5 pl-2.5 pr-1 text-xs text-[#D8DADF]"
              title={share.created_by_name ? `Geteilt von ${share.created_by_name}` : undefined}
            >
              {share.shared_with_name ?? "Nutzer"}
              {removable && (
                <button
                  type="button"
                  aria-label={`Freigabe für ${share.shared_with_name ?? "Nutzer"} entfernen`}
                  disabled={busy}
                  onClick={() => handleRemove(share)}
                  className="rounded-full p-0.5 text-[#94A3B8] hover:bg-white/10 hover:text-white disabled:opacity-45"
                >
                  <X className="size-3" />
                </button>
              )}
            </span>
          );
        })}
      </div>
      {canManage && (
        <div className="flex items-center gap-2">
          <select
            className={selectClass}
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
            aria-label="Person zum Teilen auswählen"
          >
            <option value="">Person auswählen…</option>
            {candidates.map((user) => (
              <option key={user.id} value={user.id}>
                {user.display_name ?? user.email}
              </option>
            ))}
          </select>
          <Button type="button" size="sm" variant="outline" disabled={busy || !selected} onClick={handleAdd}>
            Teilen
          </Button>
        </div>
      )}
      <ErrorBanner message={message} />
    </div>
  );
}
