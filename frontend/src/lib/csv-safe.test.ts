import { describe, expect, it } from "vitest";
import { neutralizeFormula } from "./csv-safe";

describe("neutralizeFormula", () => {
  it.each([
    ["=1+1", "'=1+1"],
    ['=HYPERLINK("http://x";"a")', `'=HYPERLINK("http://x";"a")`],
    ["@SUM(A1)", "'@SUM(A1)"],
    ["+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"],
    ["-2+3+cmd", "'-2+3+cmd"],
    ["\tTab", "'\tTab"],
  ])("entschärft die Formel %j", (input, expected) => {
    expect(neutralizeFormula(input)).toBe(expected);
  });

  it("lässt Rufnummern, negative Zahlen und normalen Text unverändert", () => {
    for (const text of ["+49 170 123-45", "-5", "Anna = Chefin", "a-b", "", "Maier"]) {
      expect(neutralizeFormula(text)).toBe(text);
    }
  });
});
