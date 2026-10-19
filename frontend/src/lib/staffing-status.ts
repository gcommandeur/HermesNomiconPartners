// NOMICON: Überlassung - EINE verständliche Statuszeile je Einsatz (reine Funktionen, testbar).
// Statt einer Liste von Meldungen zeigt der Einsatz oben einen Satz, z.B. "Bereit zur Aktivierung"
// oder "Es fehlt: Überlassungsvertrag"; die ausführlichen Texte stehen aufklappbar darunter.

export type StatusTone = "green" | "amber" | "red" | "gray";

export interface StatusLine {
  text: string;
  tone: StatusTone;
  /** Kurznamen dessen, was zur Aktivierung noch fehlt (leer, wenn nichts fehlt). */
  missing: string[];
}

export interface StatusInput {
  status: "planned" | "active" | "ended" | "aborted";
  is_overdue?: boolean;
  activation_problems?: string[];
  deadline?: {
    has_chain: boolean;
    exceeded: boolean;
    days_remaining: number | null;
    traffic: "green" | "yellow" | "red";
    equal_pay_open?: boolean;
  };
}

/** Kurznamen der fehlenden Voraussetzungen aus den ausführlichen Meldungen des Servers. */
export function missingItems(problems: string[] | undefined): string[] {
  const result: string[] = [];
  const add = (name: string) => {
    if (!result.includes(name)) result.push(name);
  };
  for (const problem of problems ?? []) {
    if (problem.includes("beginnt erst am")) add("Einsatzbeginn");
    else if (problem.includes("AÜG-Erlaubnis")) add("AÜG-Erlaubnis");
    else if (problem.includes("Überlassungsvertrag")) add("Überlassungsvertrag");
    else if (problem.includes("Pflicht-Checkliste")) {
      const open = /\(offen: ([^)]*)\)/.exec(problem)?.[1]?.split(", ").length;
      add(open ? `Checkliste (${open} ${open === 1 ? "Punkt" : "Punkte"} offen)` : "Checkliste");
    } else add(problem.length > 60 ? `${problem.slice(0, 57)}…` : problem);
  }
  return result;
}

export function assignmentStatusLine(input: StatusInput): StatusLine {
  if (input.status === "aborted") return { text: "Abgebrochen", tone: "gray", missing: [] };
  if (input.status === "ended") return { text: "Beendet", tone: "gray", missing: [] };
  if (input.status === "planned") {
    const missing = missingItems(input.activation_problems);
    return missing.length === 0
      ? { text: "Bereit zur Aktivierung", tone: "green", missing }
      : { text: `Es fehlt: ${missing.join(", ")}`, tone: "amber", missing };
  }
  const deadline = input.deadline;
  if (input.is_overdue) return { text: "Überfällig: geplantes Ende überschritten – beenden oder verlängern", tone: "red", missing: [] };
  if (deadline?.has_chain && deadline.exceeded) return { text: "Höchstüberlassungsdauer überschritten", tone: "red", missing: [] };
  if (deadline?.equal_pay_open) return { text: "Equal Pay offen: Lohn prüfen und angleichen", tone: "amber", missing: [] };
  if (deadline?.has_chain && deadline.traffic !== "green" && deadline.days_remaining !== null) {
    const days = deadline.days_remaining;
    return { text: `Frist: noch ${days} ${days === 1 ? "Tag" : "Tage"}`, tone: deadline.traffic === "red" ? "red" : "amber", missing: [] };
  }
  return { text: "Läuft planmäßig", tone: "green", missing: [] };
}
