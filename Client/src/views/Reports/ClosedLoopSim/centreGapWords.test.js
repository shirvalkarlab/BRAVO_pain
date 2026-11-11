/**
 * Decision 509: a home-record (chronic) frequency 0.5-1.0 Hz from a band's centre now answers for
 * that band (RCS08's 7.8 Hz readings at 8.5 Hz), and both pages say how far off it was sensed:
 * the Closed-Loop Source cell's hover and the Biomarkers band table's home-record cell.
 */
import { sourceCell } from "./BandSweepGridPanel";
import { chronicCountsWords } from "../Biomarkers/gridReadouts";

const WORDS = "sensed 0.7 Hz below this band's centre";

describe("home record sensed off the band's centre (decision 509)", () => {
  it("Closed-Loop: the Source hover names the gap", () => {
    const row = { decided_by: "chronic", choice_source: "chronic", pearson_r: 0.3, pearson_r_low: -0.1,
      pearson_r_high: 0.6, n_pain_reports: 14, chronic_centre_gap_words: WORDS };
    const c = sourceCell(row);
    expect(c.text).toBe("Home");
    expect(c.title).toBe(`Decided by: home record (chronic log, ${WORDS}). r +0.30 [−0.10, +0.60], n=14`);
    const plain = sourceCell({ ...row, chronic_centre_gap_words: undefined });
    expect(plain.title).toBe("Decided by: home record (chronic log). r +0.30 [−0.10, +0.60], n=14");
  });

  it("Biomarkers: the home-record cell adds the gap after the counts", () => {
    const ch = { covered: true, n_reports: 14, n_reports_in_gap: 3, n_reports_log_elsewhere: 2,
      centre_gap_words: WORDS };
    expect(chronicCountsWords(ch)).toBe(`14 matched · 3 in a gap · 2 log elsewhere · ${WORDS}`);
    expect(chronicCountsWords({ ...ch, centre_gap_words: undefined })).toBe("14 matched · 3 in a gap · 2 log elsewhere");
  });
});

describe("an established TD answer is kept; the off-centre home record is shown beside it (decision 513)", () => {
  const chronic = { covered: true, shown_beside: true, n_reports: 14, n_reports_in_gap: 3,
    n_reports_log_elsewhere: 2, pearson_r: -0.16, pearson_r_low: -0.6, pearson_r_high: 0.3,
    centre_gap_words: WORDS };

  it("Closed-Loop: the Source cell says TD and its hover gives the home record's r beside", () => {
    const row = { choice_source: "TD", pearson_r: -0.48, n_pain_reports: 72, chronic };
    const c = sourceCell(row);
    expect(c.text).toBe("TD");
    expect(c.title).toBe(`Decided by: TD. Home record shown beside, not deciding (${WORDS}): r −0.16 [−0.60, +0.30], n=14`);
  });

  it("Biomarkers: the home-record cell leads with the home r, not deciding", () => {
    expect(chronicCountsWords(chronic)).toBe(
      `home r −0.16 [−0.60, +0.30], not deciding · 14 matched · 3 in a gap · 2 log elsewhere · ${WORDS}`);
  });
});
