import { describe, expect, it } from "vitest";
import { notificationDetail, notificationHref, notificationItems } from "./notifications";

const ID = "11111111-2222-4333-8444-555555555555";
const OTHER = "99999999-8888-4777-8666-444444444444";

describe("notificationHref", () => {
  it("führt überfällige Einsätze und Vertragsmeldungen auf den Einsatz", () => {
    expect(notificationHref(`Text\n\n[staffing-overdue:${ID}:2026-02-28:${OTHER}]`)).toBe(`/ueberlassung/einsaetze/${ID}`);
    expect(notificationHref(`Text\n\n[staffing-contract:${ID}:x:${OTHER}]`)).toBe(`/ueberlassung/einsaetze/${ID}`);
  });

  it("führt Fristen und Equal Pay auf die Person, Erlaubnis auf Compliance", () => {
    expect(notificationHref(`Text\n\n[staffing-deadline:${ID}:${OTHER}:equal_pay:2026-01-01:${OTHER}]`)).toBe(`/ueberlassung/leiharbeitnehmer/${ID}`);
    expect(notificationHref(`Text\n\n[staffing-license:${ID}:2027-01-01:expiring:${OTHER}]`)).toBe("/ueberlassung/compliance");
  });

  it("liefert null ohne Kennung", () => {
    expect(notificationHref("Normale Aufgabe")).toBeNull();
    expect(notificationHref(null)).toBeNull();
  });
});

describe("notificationDetail", () => {
  it("nimmt den ersten Absatz ohne Kennung und kürzt lange Texte", () => {
    expect(notificationDetail(`Erster Absatz.\n\nZweiter.\n\n[staffing-overdue:${ID}:x:y]`)).toBe("Erster Absatz.");
    expect(notificationDetail("a".repeat(300))).toHaveLength(140);
    expect(notificationDetail(undefined)).toBe("");
  });
});

describe("notificationItems", () => {
  const now = new Date(2026, 9, 19, 12, 0, 0);
  const task = (id: string, due: string | null, title = id) => ({ id, title, description: null, due_at: due });

  it("zeigt nur fällige Aufgaben, neueste zuerst", () => {
    const items = notificationItems(
      [task("alt", "2026-10-10T05:00:00Z"), task("heute", "2026-10-19T05:00:00Z"), task("morgen", "2026-10-20T05:00:00Z"), task("ohne", null)],
      now,
    );
    expect(items.map((i) => i.id)).toEqual(["heute", "alt", "ohne"]);
  });

  it("begrenzt die Anzahl", () => {
    const many = Array.from({ length: 20 }, (_, i) => task(String(i), "2026-10-01T05:00:00Z"));
    expect(notificationItems(many, now, 5)).toHaveLength(5);
  });
});
