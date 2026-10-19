import { describe, expect, it } from "vitest";
import { assignmentStatusLine, missingItems } from "./staffing-status";

const OK_DEADLINE = { has_chain: true, exceeded: false, days_remaining: 300, traffic: "green" as const, equal_pay_open: false };

describe("missingItems", () => {
  it("kürzt die Meldungen des Servers auf Namen", () => {
    expect(
      missingItems([
        "Keine gültige AÜG-Erlaubnis für den Zeitraum 01.02.2026 bis 31.07.2026 hinterlegt.",
        "Kein Überlassungsvertrag am Einsatz verknüpft (§ 12 AÜG).",
        "Pflicht-Checkliste unvollständig (offen: Merkblatt, Sicherheitsunterweisung, PSA-Übergabeprotokoll).",
      ]),
    ).toEqual(["AÜG-Erlaubnis", "Überlassungsvertrag", "Checkliste (3 Punkte offen)"]);
  });

  it("erkennt den Einsatzbeginn und doppelte Meldungen", () => {
    expect(missingItems(["Der Einsatz beginnt erst am 01.01.2027 und kann vorher nicht aktiviert werden."])).toEqual(["Einsatzbeginn"]);
    expect(missingItems(["Der Überlassungsvertrag R-1 ist nicht aktiv (Status: Entwurf).", "Kein Überlassungsvertrag am Einsatz verknüpft"])).toEqual(["Überlassungsvertrag"]);
    expect(missingItems(["Pflicht-Checkliste unvollständig (offen: Merkblatt)."])).toEqual(["Checkliste (1 Punkt offen)"]);
    expect(missingItems(undefined)).toEqual([]);
  });
});

describe("assignmentStatusLine", () => {
  it("geplant ohne Probleme: bereit zur Aktivierung", () => {
    expect(assignmentStatusLine({ status: "planned", activation_problems: [] })).toEqual({ text: "Bereit zur Aktivierung", tone: "green", missing: [] });
  });

  it("geplant mit Problemen: eine Zeile mit dem, was fehlt", () => {
    const line = assignmentStatusLine({ status: "planned", activation_problems: ["Kein Überlassungsvertrag am Einsatz verknüpft (§ 12 AÜG)."] });
    expect(line.text).toBe("Es fehlt: Überlassungsvertrag");
    expect(line.tone).toBe("amber");
  });

  it("aktiv: überfällig vor Frist vor Equal Pay", () => {
    expect(assignmentStatusLine({ status: "active", is_overdue: true, deadline: OK_DEADLINE }).tone).toBe("red");
    expect(assignmentStatusLine({ status: "active", deadline: { ...OK_DEADLINE, exceeded: true, days_remaining: -3, traffic: "red" } }).text).toBe("Höchstüberlassungsdauer überschritten");
    expect(assignmentStatusLine({ status: "active", deadline: { ...OK_DEADLINE, equal_pay_open: true } }).text).toBe("Equal Pay offen: Lohn prüfen und angleichen");
    expect(assignmentStatusLine({ status: "active", deadline: { ...OK_DEADLINE, days_remaining: 45, traffic: "yellow" } })).toMatchObject({ text: "Frist: noch 45 Tage", tone: "amber" });
    expect(assignmentStatusLine({ status: "active", deadline: OK_DEADLINE }).text).toBe("Läuft planmäßig");
  });

  it("beendet und abgebrochen sind neutral", () => {
    expect(assignmentStatusLine({ status: "ended" }).tone).toBe("gray");
    expect(assignmentStatusLine({ status: "aborted" }).text).toBe("Abgebrochen");
  });
});
