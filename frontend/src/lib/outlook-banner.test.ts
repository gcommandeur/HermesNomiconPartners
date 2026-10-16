import { describe, expect, it } from "vitest";

import { isOutlookBannerPath, shouldShowOutlookBanner, snoozeUntil } from "./outlook-banner";

const NOW = Date.UTC(2026, 9, 16, 10, 0, 0);
const base = { state: "not_connected", pathname: "/", snoozedUntil: null, now: NOW, demo: false };

describe("shouldShowOutlookBanner", () => {
  it("zeigt den Hinweis auf Übersicht, Kalender und Mailing", () => {
    for (const pathname of ["/", "/kalender", "/mailing", "/mailing/entwuerfe"]) {
      expect(shouldShowOutlookBanner({ ...base, pathname })).toBe(true);
    }
  });

  it("zeigt ihn nirgends sonst", () => {
    for (const pathname of ["/prozesse", "/kandidaten/123", "/ueberlassung", "/einstellungen", "/kalenderx"]) {
      expect(shouldShowOutlookBanner({ ...base, pathname })).toBe(false);
    }
  });

  it("zeigt ihn nicht im Demo-Modus oder bei bestehender Verbindung", () => {
    expect(shouldShowOutlookBanner({ ...base, demo: true })).toBe(false);
    expect(shouldShowOutlookBanner({ ...base, state: "connected" })).toBe(false);
    expect(shouldShowOutlookBanner({ ...base, state: null })).toBe(false);
    expect(shouldShowOutlookBanner({ ...base, state: "needs_reconnect" })).toBe(true);
  });

  it("'Später' blendet ihn mehrere Tage aus, danach erscheint er wieder", () => {
    const until = snoozeUntil(NOW);
    expect(until - NOW).toBe(3 * 86_400_000);
    expect(shouldShowOutlookBanner({ ...base, snoozedUntil: until })).toBe(false);
    expect(shouldShowOutlookBanner({ ...base, snoozedUntil: until, now: until + 1 })).toBe(true);
  });
});

describe("isOutlookBannerPath", () => {
  it("Wurzel nur exakt", () => {
    expect(isOutlookBannerPath("/")).toBe(true);
    expect(isOutlookBannerPath("/x")).toBe(false);
  });
});
