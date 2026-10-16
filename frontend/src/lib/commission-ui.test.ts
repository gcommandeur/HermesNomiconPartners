import { describe, expect, it } from "vitest";
import { barWidth, moveItem, rankKeyFromLabel } from "./commission-ui";

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
