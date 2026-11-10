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
