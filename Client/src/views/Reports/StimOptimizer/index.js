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
*/

import { useParams } from "react-router-dom";

import { Card } from "@mui/material";

import MDBox from "components/MDBox";
import MDTypography from "components/MDTypography";
import MDAlert from "components/MDAlert";

import DatabaseLayout from "layouts/DatabaseLayout";
import { SessionController } from "database/session-control";
import { MODULES } from "database/resultCache";
import { useCachedResult } from "database/useCachedResult";

import RecomputeBar from "views/Reports/RecomputeBar";
import CacheStatusLine from "views/Reports/CacheStatusLine";
import { recomputeSlots, STIM_OPTIMIZER_SLOTS } from "views/Reports/moduleCacheKeys";
// The two-stage plan (open loop, then the check that decides whether closed loop may start, then
// closed loop) is a second request to the same endpoint, fetched after this page's own response
// has arrived and cached in its own slot; see useTwoStagePlan.js for why.
import useTwoStagePlan from "./useTwoStagePlan";
import TwoStagePlanCard from "./TwoStagePlanCard";
// The (left current, right current) surface behind decision 158's honest-current rule, and the
// home titration schedule that fills the record in where that rule fails (2026-09-14).
import CurrentMapCard from "./CurrentMapCard";
import CurrentMapScheduleCard from "./CurrentMapScheduleCard";
// The titration session to run next (2026-09-12 evening: open item 30 and the 20 s post-ramp
// margin of decision 144, joined as one recommendation), read from `data.titration_plan`.
import TitrationSessionCard from "./TitrationSessionCard";
// The decision strip: the setting programmed now beside the setting the joint search prefers,
// per side, with the gain drawn against its own uncertainty (2026-09-12, the page redesign,
// phase 1; unaffected by the 2026-09-14 joint redesign -- it already reads the two-stage plan).
import DecisionStrip from "./DecisionStrip";
// The sensing evidence behind closed-loop readiness, contacts in Medtronic form, reasons folded
// (redesign phase 3).
import SensingEvidenceTable from "./SensingEvidenceTable";
import { TYPE, HEAD } from "./typeScale";
import PAL from "views/Reports/ClosedLoopSim/palette";

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

  // A spinner is shown while a request is in flight AND on the very first paint before the hook's
  // effect has started one. Without that second condition the page would show its "no parameter
  // surface could be built" notice for one frame on every first load, which is a false statement
  // about the data rather than a cosmetic flash.
  if (loading || (!cached.hasCached && !errorText)) {
    return (
      <DatabaseLayout>
        <MDBox pt={3} display="flex" alignItems="center" justifyContent="center" gap={2}>
          <MDTypography variant="body2">
            Loading this participant&apos;s recordings and the stored settings history, and running the
            closed-loop readiness screen over every sensing contact and rate; the two-stage plan's
            own joint fit follows shortly after. About ten seconds in all; the first load after an
            ingest also rebuilds the settings history from the stored session reports and is slower.
          </MDTypography>
        </MDBox>
      </DatabaseLayout>
    );
  }

  if (errorText || !data || data.available === false) {
    return (
      <DatabaseLayout>
        <MDBox pt={3}>
          <MDAlert color="warning" dismissible={false}>
            <MDTypography variant="body2" color="white">
              No parameter surface could be built.{" "}
              {errorText || data?.reason || "This participant has no exposure epochs carrying pain reports."}
            </MDTypography>
          </MDAlert>
        </MDBox>
      </DatabaseLayout>
    );
  }

  const dm = data.design_matrix || {};

  return (
    <DatabaseLayout>
      <MDBox pt={3}>
        <MDBox display="grid" sx={{ rowGap: "16px" }}>

          {/* The Recompute control comes before the verdict, because whether the verdict was
              computed under the settings now on the page has to be readable before the verdict is
              read. Every panel below it is served from memory until it is pressed. */}
          <MDBox>
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
            <CacheStatusLine status={data ? data.cache_status : null} />
          </MDBox>

          {/* ---------- the decision: the setting in force beside the joint search's own
              preference, per side (redesign phase 1, 2026-09-12; unchanged by the joint
              redesign -- it already reads the two-stage plan, not the removed arms) ---------- */}
          <Card>
            <MDBox p={2}>
              <MDTypography variant="h6" sx={{ fontSize: TYPE.headline, mb: 1 }}>
                What the joint search prefers, per side
              </MDTypography>
              <DecisionStrip arms={{}} plan={twoStage.data} planLoading={twoStage.loading}
                planErr={twoStage.err} inForce={data.in_force_by_side || null} />
            </MDBox>
          </Card>

          {/* ---------- the sensing evidence behind closed-loop readiness ----------
              A DIFFERENT question from the strip above it: the optimizer asks which setting
              relieves pain best; this asks whether any sensed band moves with stimulation current,
              which is the only lever adaptive mode has. The per-row reasons stay, folded, because a
              refusal for want of data and a refusal on a measured negative are different clinical
              conclusions. */}
          {data.closed_loop && (
            <Card>
              <MDBox p={2}>
                <SensingEvidenceTable closedLoop={data.closed_loop} />
              </MDBox>
            </Card>
          )}

          {/* ---------- evidence base, one row of counts ---------- */}
          <Card>
            <MDBox p={2}>
              <MDBox display="flex" alignItems="baseline" gap={1} flexWrap="wrap">
                <MDTypography variant="h6" sx={{ fontSize: TYPE.section }}>Evidence base</MDTypography>
                <MDTypography variant="caption" sx={{ fontSize: TYPE.small, color: PAL.neutral }}>
                  a stretch is one continuous exposure to one setting; reports inside the wash-in are excluded
                </MDTypography>
              </MDBox>
              <MDBox mt={1.2} display="flex" columnGap={4} rowGap={1.5} flexWrap="wrap">
                {[
                  ["stretches of unchanged settings", dm.n_epochs],
                  ["pain reports used", dm.n_reports],
                  ["first to last", `${dm.t_first ? String(dm.t_first).slice(0, 10) : "—"} → ${dm.t_last ? String(dm.t_last).slice(0, 10) : "—"}`],
                  ["wash-in", data.washin_min != null ? `${data.washin_min} min` : "—"],
                  ["left currents delivered", dm.amp_mA_Left_range ? `${Number(dm.amp_mA_Left_range[0]).toFixed(1)}–${Number(dm.amp_mA_Left_range[1]).toFixed(1)} mA` : "—"],
                  ["right currents delivered", dm.amp_mA_Right_range ? `${Number(dm.amp_mA_Right_range[0]).toFixed(1)}–${Number(dm.amp_mA_Right_range[1]).toFixed(1)} mA` : "—"],
                ].map(([k, v]) => (
                  <MDBox key={k}>
                    <MDTypography variant="caption" component="div" sx={HEAD}>{k}</MDTypography>
                    <MDTypography variant="h6" sx={{ fontSize: TYPE.numLarge, fontFamily: PAL.mono, whiteSpace: "nowrap" }}>{v === null || v === undefined ? "—" : v}</MDTypography>
                  </MDBox>
                ))}
              </MDBox>
            </MDBox>
          </Card>

          {/* ---------- the titration session to run next (PI, 2026-09-12 evening) ---------- */}
          {data.titration_plan && <TitrationSessionCard plan={data.titration_plan} />}

          {/* ---------- where the two currents have been tried, and the home schedule to fill
              the record in (decision 158, 2026-09-14) -- placed directly above the two-stage
              plan card, since it is the evidence behind that card's own current recommendation
              (or the lack of one). ---------- */}
          {twoStage.data && <CurrentMapCard plan={twoStage.data} />}
          {data.current_map_schedule && <CurrentMapScheduleCard schedule={data.current_map_schedule} />}

          {/* ---------- the two-stage plan: the joint open-loop search, the gate, and closed
              loop -- the ONLY recommendation this page makes (PI, 2026-09-14) ---------- */}
          <TwoStagePlanCard plan={twoStage.data} loading={twoStage.loading} err={twoStage.err} />
        </MDBox>
      </MDBox>
    </DatabaseLayout>
  );
}
