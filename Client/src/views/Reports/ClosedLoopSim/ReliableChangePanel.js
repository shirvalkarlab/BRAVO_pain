/**
 * How big a change in this patient's own pain rating has to be before it means anything.
 *
 * WHAT THE NUMBER IS. Take every pair of ratings of one pain score that this patient filed within
 * an hour of each other while every stimulation setting stayed the same. Nothing about the therapy
 * changed between the two, so whatever difference there is between them is the patient's own
 * rating noise. The spread of those differences gives a noise floor, and 1.96 times the spread of a
 * difference gives the smallest change that could not be produced by that noise alone (decision
 * 111; Jacobson & Truax's reliable-change index with the noise measured on this patient rather
 * than borrowed from a population).
 *
 * WHY A SELECTOR. Each pain score has its own floor, on its own scale -- a 0-10 rating and a
 * 0-100 percentage cannot share one. The reader decides which score they are judging a change
 * against, so the panel shows one at a time and lets them pick (PI, 2026-09-10: "the user should
 * be able to identify which PRO value they want to focus on"). The others are still in the data.
 *
 * WHY THE PAIR COUNT IS PRINTED BESIDE THE NUMBER, ALWAYS. This floor rests on however many pairs
 * this patient happened to file within an hour of each other. On RCS08 that is 12 to 15 pairs from
 * 7 or 8 stretches of settings. A reader must see that beside the threshold, not infer it.
 *
 * WHY "GATES NOTHING" IS SAID ON THE CARD. This is a warning, not a rule (decision 104). A change
 * smaller than the floor is not "no change" -- it is a change this patient's own noise could have
 * produced with nothing therapeutic happening. That is what the card says, in those words.
 */
import { useMemo, useState } from "react";
import { Card, Select, MenuItem, FormControl } from "@mui/material";
import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import PAL from "./palette";
import { fmtNum } from "./deployFormat";

const isNum = (v) => v != null && Number.isFinite(Number(v));

function Fact({ label, value, strong }) {
  return (
    <MDBox display="flex" justifyContent="space-between" alignItems="baseline" mb={0.3}>
      <MDTypography variant="caption" sx={{ color: "#4A4A4A", mr: 1.5 }}>{label}</MDTypography>
      <MDTypography variant="caption" fontWeight={strong ? "bold" : "medium"}
        sx={{ color: "#1A1A1A", fontSize: strong ? 14 : undefined }}>
        {value}
      </MDTypography>
    </MDBox>
  );
}

export default function ReliableChangePanel({ reliableChange }) {
  const rc = reliableChange || null;
  const items = useMemo(() => (rc && rc.items) || {}, [rc]);
  const order = useMemo(() => {
    const listed = (rc && Array.isArray(rc.items_order)) ? rc.items_order : Object.keys(items);
    return listed.filter((k) => items[k]);
  }, [rc, items]);

  // Default to the first score that actually has a floor, so a fresh page never opens on
  // "not assessed" when an assessed score sits one click away.
  const firstAssessed = order.find((k) => isNum(items[k] && items[k].pooled_sd)) || order[0] || "";
  const [chosen, setChosen] = useState("");
  const key = chosen && items[chosen] ? chosen : firstAssessed;
  const it = items[key] || null;
  const v = (it && it.verdict) || null;

  const gap = rc && isNum(rc.max_gap_hours) ? Number(rc.max_gap_hours) : null;
  const gapText = gap == null ? "a short gap" : (gap === 1 ? "one hour" : `${fmtNum(gap, 1)} hours`);

  return (
    <Card sx={{ p: 2, height: "100%" }}>
      <MDTypography variant="h6" fontWeight="medium" sx={{ lineHeight: 1.3 }}>
        How big a change in this patient&apos;s own rating means anything?
      </MDTypography>
      <MDTypography variant="caption" sx={{ color: "#4A4A4A", display: "block", mb: 1 }}>
        {`Noise measured from pairs of ratings filed within ${gapText} of each other with every `}
        {"stimulation setting unchanged. Warns; blocks nothing."}
      </MDTypography>

      {order.length > 0 ? (
        <FormControl size="small" fullWidth sx={{ mb: 1.25 }}>
          <Select value={key} onChange={(e) => setChosen(e.target.value)} sx={{ fontSize: 13 }}>
            {order.map((k) => (
              <MenuItem key={k} value={k} sx={{ fontSize: 13 }}>
                {(items[k] && items[k].label) || k}
                {isNum(items[k] && items[k].pooled_sd) ? "" : "  (not assessed)"}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      ) : null}

      {it && isNum(it.pooled_sd) ? (
        <MDBox>
          <Fact strong label="Smallest change this patient's own noise cannot explain"
            value={isNum(v && v.individual_reliable_change_threshold)
              ? `${fmtNum(v.individual_reliable_change_threshold, 2)} points`
              : "—"} />
          <Fact label="Noise floor (spread of one rating)" value={`${fmtNum(it.pooled_sd, 3)} points`} />
          <Fact label="Built from"
            value={`${it.n_pairs} pair${it.n_pairs === 1 ? "" : "s"} across ${it.n_epochs} stretch${it.n_epochs === 1 ? "" : "es"} of unchanged settings`} />
          {isNum(it.n_dropped_same_minute) && it.n_dropped_same_minute > 0 ? (
            <Fact label="Same-minute repeat entries set aside" value={String(it.n_dropped_same_minute)} />
          ) : null}
          {rc && rc.population_bar ? (
            <Fact label="Population benchmark (Farrar 2001), for comparison only"
              value={`${fmtNum(rc.population_bar.points, 1)} points, or ${Math.round(100 * Number(rc.population_bar.fraction))}%`} />
          ) : null}
          {v && v.individual_verdict ? (
            <MDBox mt={1} px={1} py={0.75} borderRadius="4px" sx={{ backgroundColor: PAL.neutralFill }}>
              <MDTypography variant="caption" sx={{ color: "#333" }}>
                {/* The verdict is applied to a real pair: the highest and lowest average rating this
                    patient has shown under any one unchanged setting (decision 104). */}
                {isNum(v.change) ? `Largest swing in this record, between two settings: ${fmtNum(Math.abs(v.change), 2)} points — ` : ""}
                {v.individual_verdict}
              </MDTypography>
            </MDBox>
          ) : null}
          <MDTypography variant="caption" sx={{ color: "#6A6A6A", display: "block", mt: 1, fontSize: 10.5 }}>
            {"A change smaller than the threshold is not \"no change\" — it is a change this "}
            {"patient's own noise could produce with nothing therapeutic happening."}
          </MDTypography>
        </MDBox>
      ) : (
        <MDBox px={1} py={0.75} borderRadius="4px" sx={{ backgroundColor: PAL.warnFill }}>
          <MDTypography variant="caption" sx={{ color: PAL.warnText }}>
            {(it && it.reason) || (rc && rc.note) || "not assessed"}
          </MDTypography>
        </MDBox>
      )}
    </Card>
  );
}
