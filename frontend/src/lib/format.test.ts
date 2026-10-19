import { describe, expect, it } from "vitest";

import { formatEuroAmount, formatHours, formatNumber, formatPercent, toNumber } from "./format";

const nbsp = " ";

describe("formatNumber", () => {
  it("nutzt Komma als Dezimal- und Punkt als Tausendertrenner", () => {
    expect(formatNumber(1234.5)).toBe("1.234,5");
    expect(formatNumber(1234567.891)).toBe("1.234.567,89");
    expect(formatNumber("40.00")).toBe("40");
    expect(formatNumber(7.5, { min: 2 })).toBe("7,50");
  });

  it("behandelt null, leer und ungültige Werte", () => {
    expect(formatNumber(null)).toBe("–");
    expect(formatNumber(undefined)).toBe("–");
    expect(formatNumber("")).toBe("–");
    expect(formatNumber("abc")).toBe("–");
  });

  it("kennt die Null und negative Werte", () => {
    expect(formatNumber(0)).toBe("0");
    expect(formatNumber("0.00", { min: 2 })).toBe("0,00");
    expect(formatNumber(-1234.5)).toBe("-1.234,5");
    expect(formatNumber(-0.5)).toBe("-0,5");
  });
});

describe("formatHours / formatPercent / formatEuroAmount", () => {
  it("Stunden ohne und mit festen Nachkommastellen", () => {
    expect(formatHours("40.00")).toBe("40 Std.");
    expect(formatHours("38.5")).toBe("38,5 Std.");
    expect(formatHours(7.5, { fixed: true })).toBe("7,50 Std.");
    expect(formatHours(7.5, { fixed: true, unit: "" })).toBe("7,50");
    expect(formatHours(null)).toBe("–");
  });

  it("Prozent ohne überflüssige Nullen", () => {
    expect(formatPercent("30.00")).toBe("30 %");
    expect(formatPercent(27.5)).toBe("27,5 %");
    expect(formatPercent(-2)).toBe("-2 %");
    expect(formatPercent(null)).toBe("–");
  });

  it("Euro mit zwei Nachkommastellen", () => {
    expect(formatEuroAmount("14.5")).toBe(`14,50${nbsp}€`);
    expect(formatEuroAmount(1234567.8)).toBe(`1.234.567,80${nbsp}€`);
    expect(formatEuroAmount(0)).toBe(`0,00${nbsp}€`);
    expect(formatEuroAmount(-5)).toBe(`-5,00${nbsp}€`);
    expect(formatEuroAmount(undefined)).toBe("–");
  });

  it("toNumber", () => {
    expect(toNumber("12.5")).toBe(12.5);
    expect(toNumber("x")).toBeNull();
  });
});
