/**
=========================================================
* UF BRAVO Platform -- Stimulation Parameter Optimizer (Shirvalkar Lab)
=========================================================
* Renders the two-stage plan returned by /api/queryStimOptimizer: the open-loop search fitted
* JOINTLY over both stimulators, the check that decides whether closed loop may start, and closed
* loop itself.
*
* REMOVED 2026-09-14, on the PI's direct instruction, verbatim: "Get rid of the whole arm strip
* and chart display. That arm thing doesn't make any sense and shouldn't belong there. Only keep
* the newer two-stage plan." This page used to fit the Left and the Right hemisphere as two
* INDEPENDENT (rate, amplitude) surfaces ("arms"), show them as a small-multiples strip with a
* chart, and let a reader pick one arm to see its five model surfaces and its own "what to test
* next" queue. That whole path -- the per-arm headline banner, the blockers fold under it, the
* "Arms" strip and its chart, and the per-arm figures-and-queue card -- is gone, because the
* search underneath it modelled the two stimulators as if changing one side's current could not
* possibly matter to the other side's own reading, when in fact both currents are reprogrammed
* CONCURRENTLY on this device (there is one shared rate column in the settings history, never a
* per-side rate) and are never held apart during actual programming. `StimOptimizer.pipeline.run`,
* the function that fitted those two independent surfaces, is UNCHANGED and still fully tested; it
* is simply not called by the server on this page's own request any more (see
* `StimOptimizer/bravo_service.py`, `run_for_participant`).
*
* What replaces it: Stage 1 now fits ONE joint (rate, amplitude-Left, amplitude-Right) surface per
* stratum and freezes ONE configuration for both sides at once, shown here as the decision strip,
* the two-stage plan card, and the titration-session card.
*
* THE DESIGN REVIEW OF 2026-09-26 (`artifacts/design_review_2026-09-26_stim_optimizer_and_biomarkers.md`
* §1; the PI: "yes to all six, build them"): a status line above the readiness card (amends
* decision 243's order by one line; no card moved); the stored-results line beside the recompute
* bar folds (this page wraps it; RecomputeBar.js and CacheStatusLine.js are not edited); the home
* schedule is a section of the next-visit card (amends the two-cards ruling of 2026-09-12); the
* control analyses fold; the loading message is one line.
*
* THE MINIMALIST REDESIGN OF 2026-09-26 (`artifacts/design_2026-09-26_minimalist_redesign/SPEC.md`
* section 5.3): the page opens with its answer. The title is its question ("Should today's setting
* change, and can closed loop start?"); one grey line names the pain score; the status sentence;
* the status list (✕ blocks, ▲ needs more data or caution, ○ not checked, at most five items); the
* safe current ceiling, read from the response and never typed here; a slim contents row. Then the
* recompute bar (the PI's file, unchanged) and four sections, each a question: is any setting proven
* better than today's; where have currents been tried; can closed loop start; what must the next
* visit deliver. The evidence base is a quiet footer; the research checks fold. Colours, sizes and
* spacing come from the shared tokens; the page no longer borrows the Closed-Loop page's palette.
*/

import { useParams } from "react-router-dom";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";

import DatabaseLayout from "layouts/DatabaseLayout";
import { SessionController } from "database/session-control";
import { MODULES } from "database/resultCache";
import { useCachedResult } from "database/useCachedResult";

import { LAYOUT } from "assets/theme/base/tokens";
import RecomputeBar from "views/Reports/RecomputeBar";
import CacheStatusLine from "views/Reports/CacheStatusLine";
import { recomputeSlots, STIM_OPTIMIZER_SLOTS } from "views/Reports/moduleCacheKeys";
import Section from "views/Reports/paper/Section";
import CeilingLine from "views/Reports/paper/CeilingLine";
import PageHead from "views/Reports/paper/PageHead";
import { JumpRow } from "views/Reports/paper/links";
import useDocumentTitle from "views/Reports/paper/useDocumentTitle";
import { useStudyCode } from "views/Reports/paper/studyCode";
import { painScoreLabel } from "views/Reports/painScores";
// The two-stage plan (open loop, then the check that decides whether closed loop may start, then
// closed loop) is a second request to the same endpoint, fetched after this page's own response
// has arrived and cached in its own slot; see useTwoStagePlan.js for why.
import useTwoStagePlan from "./useTwoStagePlan";
import TwoStagePlanCard from "./TwoStagePlanCard";
// The (left current, right current) surface behind the honest-current rule, and the home
// titration schedule that fills the record in where that rule fails (2026-09-14).
import CurrentMapCard from "./CurrentMapCard";
import CurrentMapScheduleCard from "./CurrentMapScheduleCard";
// The titration session to run next, read from `data.titration_plan`.
import TitrationSessionCard from "./TitrationSessionCard";
// The decision: the setting programmed now beside the setting the joint search suggests, per side,
// with the gain drawn against its own uncertainty.
import DecisionStrip, { decisionHeadline } from "./DecisionStrip";
// The sensing evidence behind closed-loop readiness.
import SensingEvidenceTable from "./SensingEvidenceTable";
import { T, TYPE, SizedFold } from "./typeScale";
// The page's status sentence and list: the answer, then why, in ✕ ▲ ○ items of five words or fewer.
import StatusLine, { StatusSentence } from "./StatusLine";
import { ceilingFromResponse } from "./ceiling";
import { ControlAnalysesSection } from "views/Reports/ControlAnalyses/ControlAnalysesCard";

/** The page's question, its title (SPEC.md section 5.3). */
export const PAGE_QUESTION = "Should today's setting change, and can closed loop start?";

/** The browser tab's title while this page is shown (TASTE_AUDIT.md C7, the PI's wording). */
export const TAB_TITLE = "Stim optimizer";

/** The slim contents row under the status list (SPEC.md section 4, rule 7). Drawn by the shared
 *  jump-link row: separated by space only, never "·" (C11), and not underlined (C3). */
export const CONTENTS = [
  ["decision", "Proven better?"],
  ["current-map", "Currents tried"],
  ["closed-loop", "Closed loop"],
  ["next-visit", "Next visit"],
];

/** The pain score the decision is fitted on, as the page's own label ("Left Leg VAS"). */
function primaryPainScore(plan) {
  const st = (plan && plan.stage1) || {};
  const key = (st.frozen_configuration || {}).primary_item || ((plan && plan.manifest) || {}).primary_item
    || st.primary_item || null;
  if (!key) return null;
  const k = String(key);
  return painScoreLabel(/_vas$/.test(k) || k === "nrs" || k === "vas" ? k : `${k}_vas`);
}

/**
 * THE REQUEST THIS VIEW SENDS, WRITTEN OUT IN FULL RATHER THAN LEFT TO THE SERVER'S DEFAULTS.
 *
 * The endpoint takes six optional parameters besides the participant — the pain sites, the
 * hemispheres, the wash-in exclusion window, the figure backend, and the depth and width of the
 * forward simulation the two-stage path's own Stage 1 runs. They are documented on
 * `QueryStimOptimizer` in `BRAVO/Server/APIs/DataAnalysis.py` and applied in
 * `modules/StimOptimizer/bravo_service` `run_for_participant`, and the values below are exactly
 * those documented defaults. The request is therefore unchanged in what it asks the server for.
 *
 * What changes is that it is now written down here, which is what allows the result cache to key
 * on it. A cache key has to name everything that changes the answer; a request that relies on the
 * server's defaults names none of it, so a key derived from such a request would be blind to the
 * very parameters this page is about.
 */
const OPTIMIZER_REQUEST = {
  Sites: ["left_leg", "back"],
  Hemispheres: ["Left", "Right"],
  WashinMin: 1.0,
  Backend: "none",
  NBatches: 3,
  Q: 4,
};

export default function StimOptimizer() {
  const { participant_uid } = useParams();
  // The tab's title is the page's question in the PI's words, from the first paint on, the
  // loading notice included (TASTE_AUDIT.md C7); the page head leaves it alone.
  useDocumentTitle(TAB_TITLE);

  const cached = useCachedResult({
    moduleKey: MODULES.stimOptimizer,
    uid: participant_uid,
    // The request, minus the participant, is the cache key: the participant is already the other
    // half of the cache slot, so including it would put the same value in the key twice.
    settings: OPTIMIZER_REQUEST,
    enabled: !!participant_uid,
    fetcher: () => SessionController.query("/api/queryStimOptimizer",
      { ParticipantId: participant_uid, ...OPTIMIZER_REQUEST })
      .then((response) => (response && response.data) || {}),
  });

  const data = cached.data;
  const loading = cached.loading;
  const errorText = cached.err;

  // THE TWO-STAGE PLAN IS FETCHED ONLY ONCE THE PAGE'S OWN RESPONSE HAS ARRIVED. `afterMain` is
  // this page's `data`; while it is null the hook issues nothing, so the first paint is unchanged.
  // Called here, before any early return, because a hook must run on every render.
  const twoStage = useTwoStagePlan({
    participantUid: participant_uid,
    baseRequest: OPTIMIZER_REQUEST,
    afterMain: cached.data,
  });
  // The de-identified study code for the line under the title (SPEC section 4 rule 1); null when
  // the participant record carries none.
  const participantCode = useStudyCode(participant_uid);

  // A spinner is shown while a request is in flight AND on the very first paint before the hook's
  // effect has started one. Without that second condition the page would show its "no parameter
  // surface could be built" notice for one frame on every first load, which is a false statement
  // about the data rather than a cosmetic flash.
  if (loading || (!cached.hasCached && !errorText)) {
    return (
      <DatabaseLayout>
        <MDBox pt={3} display="flex" alignItems="center" justifyContent="center" gap={2}>
          <MDTypography variant="body2" sx={{ fontSize: TYPE.body, color: T.ink2 }}>
            Loading the settings history and the readiness check, about 10 s (longer after an ingest).
          </MDTypography>
        </MDBox>
      </DatabaseLayout>
    );
  }

  if (errorText || !data || data.available === false) {
    return (
      <DatabaseLayout>
        <MDBox pt={3} sx={{ maxWidth: LAYOUT.contentMax, mx: "auto" }}>
          <MDTypography variant="body2" component="p" sx={{ fontSize: TYPE.lead, color: T.ink }}>
            {"○ No parameter surface could be built. "}
            {errorText || data?.reason || "This participant has no stretches of unchanged settings carrying pain reports."}
          </MDTypography>
        </MDBox>
      </DatabaseLayout>
    );
  }

  const dm = data.design_matrix || {};
  const ceiling = ceilingFromResponse(data, twoStage.data);
  const painScore = primaryPainScore(twoStage.data);

  return (
    <DatabaseLayout>
      <MDBox pt={3} pb={8} sx={{ maxWidth: LAYOUT.contentMax, mx: "auto", color: T.ink2 }}>

        {/* ---------- how the page opens (SPEC.md section 4, rule 1): the question, the pain score,
            the answer, why (at most five items, each with its glyph), the safe ceiling read from
            the response, and the contents row. Nothing in the head is folded. ---------- */}
        <PageHead title={PAGE_QUESTION} participant={participantCode} painScore={painScore}
          documentTitle=""
          status={<StatusSentence data={data} plan={twoStage.data} planLoading={twoStage.loading} />}>
          {/* The status list, its key and its fold (this page's own: its items carry the
              decision-294 dagger and fold what each rests on), then the ceiling line and the
              contents row. Built on the shared page head (TASTE_AUDIT.md C6). */}
          <StatusLine data={data} plan={twoStage.data} planLoading={twoStage.loading} showHeadline={false} />
          <MDBox mt={1.5}>
            <CeilingLine leftMa={ceiling.leftMa} rightMa={ceiling.rightMa} />
          </MDBox>
          <MDBox mt={2}>
            <JumpRow label="Contents" items={CONTENTS.map(([id, label]) => ({ href: `#${id}`, label }))} />
          </MDBox>
        </PageHead>

        {/* The Recompute control (the PI's own file, unchanged): every section below is served from
            memory until it is pressed. When the stored results were built: one click away. */}
        <MDBox mb={4}>
          <RecomputeBar
            title="stim parameter optimizer"
            stale={cached.stale}
            staleReasons={cached.staleReasons}
            computedAt={cached.computedAt}
            loading={cached.loading}
            notKept={cached.notKept}
            // Both slots: the page's own response and the two-stage plan fetched after it.
            onRecompute={() => recomputeSlots(participant_uid, STIM_OPTIMIZER_SLOTS)}
          />
          {data && data.cache_status ? (
            <SizedFold show="When the stored results were built" hide="Hide" dense mt={0.5}>
              <MDBox data-testid="cache-status-fold-body">
                <CacheStatusLine status={data.cache_status} />
              </MDBox>
            </SizedFold>
          ) : null}
        </MDBox>

        {/* ---------- 1. is any setting proven better than today's? The answer is COMPUTED from the
            per-side verdicts in the same render, never a fixed description of the method. -------- */}
        <Section id="decision" question="Is any setting proven better than today's?"
          answer={`${decisionHeadline(twoStage.data, data.in_force_by_side || null)}.`}>
          <DecisionStrip arms={{}} plan={twoStage.data} planLoading={twoStage.loading}
            planErr={twoStage.err} inForce={data.in_force_by_side || null} />
        </Section>

        {/* ---------- 2. where have currents been tried, and what does the fit predict? ---------- */}
        {twoStage.data && <CurrentMapCard plan={twoStage.data} />}

        {/* ---------- 3. can closed loop start? The allowed sensing pairs as sentence blocks, the
            other combinations folded, then the four checks and what closed loop ruled out. ---------- */}
        <Section id="closed-loop" question="Can closed loop start?" collapsible>
          {data.closed_loop && <SensingEvidenceTable closedLoop={data.closed_loop} />}
          <MDBox mt={3}>
            <TwoStagePlanCard plan={twoStage.data} loading={twoStage.loading} err={twoStage.err} />
          </MDBox>
        </Section>

        {/* ---------- 4. what must the next visit deliver? The session to run in clinic, and the
            home schedule inside it (the PI amended his two-cards ruling on 2026-09-26). ---------- */}
        {data.titration_plan && (
          <TitrationSessionCard plan={data.titration_plan} participantUid={participant_uid}
            homeSchedule={data.current_map_schedule || null} />
        )}
        {/* No titration plan on the response: the home schedule still shows, as its own section. */}
        {!data.titration_plan && data.current_map_schedule && (
          <Section id="next-visit" question="What must the next visit deliver?">
            <CurrentMapScheduleCard schedule={data.current_map_schedule} />
          </Section>
        )}

        {/* ---------- the evidence base, a quiet footer (no decision on the page reads it) ---------- */}
        <MDBox data-testid="evidence-base-footer" mt={2}>
          <MDTypography variant="caption" component="div" sx={{ fontSize: TYPE.small, lineHeight: "18px", color: T.ink3 }}>
            {`Evidence base: ${dm.n_epochs ?? "—"} stretches of unchanged settings · ${dm.n_reports ?? "—"} pain reports used · `
              + `${dm.t_first ? String(dm.t_first).slice(0, 10) : "—"} → ${dm.t_last ? String(dm.t_last).slice(0, 10) : "—"} · `
              + `ratings in the first ${data.washin_min != null ? `${data.washin_min} min` : "—"} after a setting change left out · `
              + `left currents delivered ${dm.amp_mA_Left_range ? `${Number(dm.amp_mA_Left_range[0]).toFixed(1)}–${Number(dm.amp_mA_Left_range[1]).toFixed(1)} mA` : "—"} · `
              + `right ${dm.amp_mA_Right_range ? `${Number(dm.amp_mA_Right_range[0]).toFixed(1)}–${Number(dm.amp_mA_Right_range[1]).toFixed(1)} mA` : "—"} (history, not a proposal). `
              + "A stretch is one continuous exposure to one setting."}
          </MDTypography>
        </MDBox>

        {/* ---------- the research checks: saved, dated, run offline; they feed nothing above.
            Folded, still mounted, so it loads. ---------- */}
        <SizedFold show="Checks against chance and against the current (run offline)" hide="Hide the research checks" mt={3}>
          <ControlAnalysesSection participantUid={participant_uid} page="stim_optimizer" />
        </SizedFold>
      </MDBox>
    </DatabaseLayout>
  );
}
