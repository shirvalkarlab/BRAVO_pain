"""The Closed-Loop robustness answer keeps one saved entry per candidate (decision 309).

The robustness bootstrap is filed under a key that names the candidate (sensing pair, band centre,
side) and is read back by the candidate tag on its sidecar, exactly like the CL-DBS simulation and
the design rule. Those two keep six entries a participant; the robustness kind kept the store's
default of ONE, so writing the right candidate's answer deleted the left's, and the next report for
the left rebuilt it (the decision-107 failure, found by decision 306's agent on 2026-09-26). Two
candidates written in turn must both read back, each as its own.
"""
try:
    from modules.CacheStore import ledger as _ledger, store as st
    from modules.ClosedLoopDeployment import adapter as AD, robustness as RB
except ImportError:                                              # pragma: no cover - host runner
    from CacheStore import ledger as _ledger, store as st
    from ClosedLoopDeployment import adapter as AD, robustness as RB


def test_the_left_and_right_candidates_robustness_answers_both_survive_and_each_is_found(tmp_path):
    assert st.KEEP_NEWEST_BY_KIND.get(RB.KIND, 1) >= 2, "one entry per participant evicts a side"
    uid = "p-robustness-cands"
    prev = st.DIR_OVERRIDE, _ledger.ENABLED, AD._SHARED_CACHE_DIR_OVERRIDE
    st.DIR_OVERRIDE, _ledger.ENABLED, AD._SHARED_CACHE_DIR_OVERRIDE = str(tmp_path), False, str(tmp_path)
    try:
        cands = (("ONE_THREE_LEFT", 24.5, "Left"), ("ZERO_THREE_RIGHT", 24.5, "Right"))
        for ch, fc, side in cands:
            st.store(RB.KIND, uid, (RB.KIND, RB.RULE_VERSION, ch, fc, side), {"for": ch},
                     writer="closed_loop", trigger="deployment_report", provenance=[],
                     extra={"candidate": AD._simulation_candidate_tag(ch, fc, side)})
        got = {ch: AD.robustness_if_stored(uid, {"channel": ch, "center_hz": fc,
                                                 "actuated_hemisphere": side}, hemisphere=side)
               for ch, fc, side in cands}
        assert got == {"ONE_THREE_LEFT": {"for": "ONE_THREE_LEFT"},
                       "ZERO_THREE_RIGHT": {"for": "ZERO_THREE_RIGHT"}}, got
        # a candidate never written is not answered with another candidate's entry
        assert AD.robustness_if_stored(uid, {"channel": "ONE_THREE_LEFT", "center_hz": 12.5,
                                             "actuated_hemisphere": "Left"}) is None
    finally:
        # cleared only while this test's own directory override is in force (decisions 116, 129)
        st.clear()
        st.DIR_OVERRIDE, _ledger.ENABLED, AD._SHARED_CACHE_DIR_OVERRIDE = prev
