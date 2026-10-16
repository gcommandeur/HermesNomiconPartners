import { describe, expect, it } from "vitest";

import type { CandidateSubmission } from "./api/types";
import { pipelineKpis } from "./fee-forecast";

const NOW = new Date(2026, 9, 16, 10, 0, 0);

function process(partial: Partial<CandidateSubmission>): CandidateSubmission {
  return {
    status: "interview",
    expected_fee: null,
    closing_probability: null,
    follow_up_at: null,
    archived_at: null,
    ...partial,
  } as CandidateSubmission;
}

describe("pipelineKpis", () => {
  it("summiert die Fees laufender Prozesse und gewichtet nur mit vorhandener Wahrscheinlichkeit", () => {
    const kpis = pipelineKpis(
      [
        process({ expected_fee: "10000", closing_probability: 0.5 }),
        process({ status: "offer", expected_fee: "20000", closing_probability: 0.25 }),
        process({ expected_fee: "8000" }), // ohne Wahrscheinlichkeit: zählt im Pipeline-Wert, nicht gewichtet
        process({ expected_fee: null }), // Fee offen
      ],
      NOW,
    );
    expect(kpis.pipelineValue).toBe(38000);
    expect(kpis.expectedWeighted).toBe(10000);
    expect(kpis.openFees).toBe(1);
  });

  it("ignoriert Platzierungen, Stornos und Archiviertes", () => {
    const kpis = pipelineKpis(
      [
        process({ status: "placement", expected_fee: "50000", closing_probability: 1 }),
        process({ status: "cancelled", expected_fee: "9000" }),
        process({ expected_fee: "7000", closing_probability: 1, archived_at: "2026-10-01T00:00:00Z" }),
      ],
      NOW,
    );
    expect(kpis.pipelineValue).toBe(0);
    expect(kpis.expectedWeighted).toBe(0);
  });

  it("zählt überfällige Nachfass-Termine", () => {
    const kpis = pipelineKpis(
      [
        process({ follow_up_at: new Date(2026, 9, 10).toISOString() }),
        process({ follow_up_at: new Date(2026, 9, 20).toISOString() }),
      ],
      NOW,
    );
    expect(kpis.overdueFollowUps).toBe(1);
  });
});
