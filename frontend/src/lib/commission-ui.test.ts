import { describe, expect, it } from "vitest";
import { barWidth, daysToQuarterEndText, monthLabel, moveItem, nextRoleText, provisionalNote, quarterBoundaryLabels, rankKeyFromLabel, timelineChartData, type TimelineMonthLike } from "./commission-ui";

describe("barWidth", () => {
  it("begrenzt auf 0 bis 100", () => {
    expect(barWidth("41.7")).toBe(41.7);
    expect(barWidth(120)).toBe(100);
    expect(barWidth(-5)).toBe(0);
  });
  it("behandelt fehlende oder ungültige Werte als 0", () => {
    expect(barWidth(null)).toBe(0);
    expect(barWidth(undefined)).toBe(0);
    expect(barWidth("abc")).toBe(0);
  });
});

describe("rankKeyFromLabel", () => {
  it("bildet einen gültigen Schlüssel aus dem Namen", () => {
    expect(rankKeyFromLabel("Senior Berater", [])).toBe("senior_berater");
    expect(rankKeyFromLabel("Größe & Übung", [])).toBe("groesse_uebung");
  });
  it("hält den Schlüssel eindeutig", () => {
    expect(rankKeyFromLabel("Manager", ["manager"])).toBe("manager_2");
    expect(rankKeyFromLabel("Manager", ["manager", "manager_2"])).toBe("manager_3");
  });
  it("fällt bei leerem Namen auf stufe zurück", () => {
    expect(rankKeyFromLabel("   ", [])).toBe("stufe");
  });
});

describe("moveItem", () => {
  it("verschiebt ein Element", () => {
    expect(moveItem(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(moveItem(["a", "b", "c"], 1, 1)).toEqual(["a", "c", "b"]);
  });
  it("lässt die Liste an den Rändern unverändert", () => {
    const items = ["a", "b"];
    expect(moveItem(items, 0, -1)).toBe(items);
    expect(moveItem(items, 1, 1)).toBe(items);
  });
});

describe("Zeitstrahl", () => {
  const month = (year: number, m: number, extra: Partial<TimelineMonthLike> = {}): TimelineMonthLike => ({
    year,
    month: m,
    quarter: Math.floor((m - 1) / 3) + 1,
    month_in_quarter: ((m - 1) % 3) + 1,
    revenue: "1000.00",
    commission: "100.00",
    is_current: false,
    is_provisional: false,
    ...extra,
  });

  it("beschriftet Monate deutsch", () => {
    expect(monthLabel(2026, 10)).toBe("Okt 26");
    expect(monthLabel(2026, 3, true)).toBe("März 2026");
  });

  it("macht aus den Monaten Diagrammdaten mit Quartalsgrenzen und markiertem laufenden Monat", () => {
    const months = [month(2026, 8), month(2026, 9), month(2026, 10), month(2026, 11, { is_current: true })];
    const data = timelineChartData(months);
    expect(data.map((d) => d.label)).toEqual(["Aug 26", "Sep 26", "Okt 26", "Nov 26"]);
    expect(data.map((d) => d.revenue)).toEqual([1000, 1000, 1000, 1000]);
    expect(data.filter((d) => d.isCurrent).map((d) => d.label)).toEqual(["Nov 26"]);
    expect(quarterBoundaryLabels(data)).toEqual(["Okt 26"]);
  });

  it("setzt am ersten angezeigten Monat keine Quartalsgrenze, auch wenn er ein Quartalsbeginn ist", () => {
    expect(quarterBoundaryLabels(timelineChartData([month(2026, 7), month(2026, 8)]))).toEqual([]);
  });

  it("beschreibt den Fortschritt zur nächsten Rolle", () => {
    const text = nextRoleText({
      is_top_rank: false,
      current_rank_label: "Senior Consultant",
      next_rank_label: "Manager",
      quarter_revenue: "68000.00",
      hurdle: "96000",
      remaining: "28000.00",
      days_to_quarter_end: 41,
    });
    expect(text.replace(/ /g, " ")).toBe("Senior Consultant → Manager: 68.000 € von 96.000 € Quartalsumsatz, noch 28.000 €");
  });

  it("meldet erreichte Schwelle und die höchste Stufe", () => {
    const reached = nextRoleText({ is_top_rank: false, current_rank_label: "Consultant", next_rank_label: "Specialist Consultant", quarter_revenue: "50000", hurdle: "48000", remaining: "0.00", days_to_quarter_end: 3 });
    expect(reached).toContain("Schwelle erreicht");
    const top = nextRoleText({ is_top_rank: true, current_rank_label: "Director", quarter_revenue: "70000", next_band_remaining: "15000.00", next_band_rate: "37.5", days_to_quarter_end: 3 });
    expect(top.replace(/ /g, " ")).toBe("Director (höchste Stufe): noch 15.000 € bis zur nächsten Provisionsstufe (dann 37,5 %)");
    expect(nextRoleText({ is_top_rank: true, current_rank_label: "Director", quarter_revenue: "200000", days_to_quarter_end: 3 })).toContain("höchster Provisionssatz erreicht");
  });

  it("nennt die Tage bis Quartalsende", () => {
    expect(daysToQuarterEndText(41)).toBe("noch 41 Tage bis Quartalsende");
    expect(daysToQuarterEndText(1)).toBe("noch 1 Tag bis Quartalsende");
    expect(daysToQuarterEndText(0)).toBe("letzter Tag des Quartals");
  });

  it("kennzeichnet den laufenden Monat als vorläufig", () => {
    expect(provisionalNote(true)).toContain("vorläufig");
    expect(provisionalNote(false)).toContain("Ohne Rang");
  });
});
