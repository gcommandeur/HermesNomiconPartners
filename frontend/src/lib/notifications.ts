// NOMICON: Glocke - Meldungen aus den vorhandenen Aufgaben (reine Funktionen, testbar).
// Es gibt keinen neuen Kanal: der Tagesjob der Überlassung legt Aufgaben an (Fristen, Equal Pay,
// überfällige Einsätze, fehlende Verträge, Erlaubnis); die Glocke zeigt die offenen, fälligen
// Aufgaben der angemeldeten Person kurz an. Die Texte enthalten nie Lohn- oder Margenwerte.

export interface NotificationTask {
  id: string;
  title: string;
  description?: string | null;
  due_at?: string | null;
}

export interface NotificationItem {
  id: string;
  title: string;
  detail: string;
  href: string | null;
}

const MAX_DETAIL = 140;

/** Ziel der Meldung aus der Kennung am Ende der Aufgabenbeschreibung ("[staffing-overdue:<id>:…]"). */
export function notificationHref(description: string | null | undefined): string | null {
  const text = description ?? "";
  const assignment = /\[staffing-(?:overdue|contract):([0-9a-f-]{36})/i.exec(text)?.[1];
  if (assignment) return `/ueberlassung/einsaetze/${assignment}`;
  const worker = /\[staffing-deadline:([0-9a-f-]{36})/i.exec(text)?.[1];
  if (worker) return `/ueberlassung/leiharbeitnehmer/${worker}`; // leitet auf das Kandidatenprofil weiter
  if (/\[staffing-license:/i.test(text)) return "/ueberlassung/compliance";
  return null;
}

/** Erster Absatz der Beschreibung ohne Kennung, gekürzt. */
export function notificationDetail(description: string | null | undefined): string {
  const first = (description ?? "").split(/\n\s*\n/)[0]?.replace(/\[staffing-[^\]]*\]/g, "").trim() ?? "";
  return first.length > MAX_DETAIL ? `${first.slice(0, MAX_DETAIL - 1)}…` : first;
}

/** Fällige offene Aufgaben (heute oder früher, neueste zuerst) als Meldungen. */
export function notificationItems(tasks: NotificationTask[], now: Date = new Date(), limit = 8): NotificationItem[] {
  const endOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999).getTime();
  return tasks
    .filter((task) => !task.due_at || new Date(task.due_at).getTime() <= endOfToday)
    .sort((a, b) => new Date(b.due_at ?? 0).getTime() - new Date(a.due_at ?? 0).getTime())
    .slice(0, limit)
    .map((task) => ({
      id: task.id,
      title: task.title,
      detail: notificationDetail(task.description),
      href: notificationHref(task.description),
    }));
}
