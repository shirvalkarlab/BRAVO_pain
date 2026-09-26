"""Which control analyses exist, which page shows each, and the literature behind it.

A page draws the newest saved result of each of its analyses, in `order`. The literature links
point at the reports of 2026-09-24 in the repository, which every reader of the page can open.
"""

REPO_BLOB = "https://github.com/shirvalkarlab/BRAVO_pain/blob/PS_closedloop_deployment/artifacts/"

LIT = {
    "synthesis": ("Synthesis: same current, wash-in, one threshold, the 0 mA periods",
                  "research_2026-09-24_SYNTHESIS_state_washin_threshold_offperiods.md"),
    "state": ("Literature: the same current doing different things",
              "research_2026-09-24_1_same_current_different_effect.md"),
    "washin": ("Literature: wash-in and stimulation history",
               "research_2026-09-24_2_wash_in_and_dose_history.md"),
    "threshold": ("Literature: tonic current and a single band-power threshold",
                  "research_2026-09-24_3_tonic_current_and_single_threshold.md"),
    "zero_ma": ("Literature: the 0 mA period as a test",
                "research_2026-09-24_4_zero_mA_period_as_a_test.md"),
    "rtm": ("Literature: regression to the mean and decision 253's swing",
            "research_2026-09-25_options/01_regression_to_the_mean.md"),
    "critique": ("Critique: the day-to-day correlation of ratings (M2) and the electrical-artifact "
                "alternative (M1)", "research_2026-09-25_options/08_critique_science.md"),
    "revised_plan": ("The revised plan: items A4 and A5", "research_2026-09-25_options/11_REVISED_PLAN.md"),
    "band_detector": ("Report: the research band detector and its three choices",
                      "research_2026-09-25_options/04_band_detector.md"),
    "rulings_0925": ("The PI's rulings of 2026-09-25 (answers 5a-5c)",
                     "research_2026-09-25_options/11_REVISED_PLAN.md"),
}


def _lit(*names):
    return [{"label": LIT[n][0], "url": REPO_BLOB + LIT[n][1]} for n in names]


PAGES = ("biomarkers", "stim_optimizer")

ANALYSES = {
    "zero_ma_within_stretch": dict(
        page="biomarkers", order=1,
        title="Band against pain with the current off",
        what=("Within each stretch when both sides were at 0 mA, and the stretch with the left off "
              "and the right on, the correlation of each band's power with pain; ratings matched to "
              "the nearest recording the same day; intervals resample whole days; q corrects for 22 bands."),
        literature=_lit("synthesis", "zero_ma")),
    "current_explains": dict(
        page="biomarkers", order=2,
        title="What the stimulation current explains",
        what=("Pain read out of sample from the current alone, from every band, and from every band "
              "with the current taken out, against shuffled data that keeps pain's own persistence; "
              "the page's 60-minute matching."),
        literature=_lit("synthesis", "threshold")),
    "time_of_day": dict(
        page="biomarkers", order=3,
        title="Time of day and weekends",
        what=("Whether band power follows the California clock or the weekend, per sensing pair and "
              "band, and how much the weekend moves the band-to-pain correlation."),
        literature=_lit("synthesis", "state")),
    "band_detector_research": dict(
        page="biomarkers", order=4,
        title="Band detector, research version (pain as a number)",
        what=("Every band of one sensing pair read together (a ridge regression), predicting the pain "
              "score itself on held-out blocks of time with the neighbouring ratings dropped; scored by "
              "the rank correlation between prediction and rating within each held-out block (0 is chance, "
              "never folded), plainly "
              "and with the stimulation current taken out of the bands and the pain as a curve; the "
              "current alone beside it; and every band inside the longest run at one unchanged current. "
              "The page's 60-minute matching. REDCap ratings only, unless the page's clinic-sheet "
              "switch is on, which shows the run with the sheet ratings merged in."),
        literature=_lit("band_detector", "rulings_0925")),
    "band_detector_device": dict(
        page="biomarkers", order=5,
        title="Band detector, device-shaped version (one band, two pain groups)",
        what=("What the device could read: one band at a time, pain split into two groups by the page's "
              "own split, the area under the curve from a logistic regression of the two groups on band "
              "power fitted on held-out blocks of time, scored within each block; the band power at the device's own timing "
              "(3-second averaged readings, held for the onset time, the start-up delay skipped), "
              "plainly and with the current taken out as a curve; q corrects for the 22 bands of a "
              "pair. REDCap ratings only, unless the page's clinic-sheet switch is on, which shows the "
              "run with the sheet ratings merged in."),
        literature=_lit("band_detector", "rulings_0925")),
    "current_with_memory": dict(
        page="stim_optimizer", order=1,
        title="A current with memory (wash-in)",
        what=("Pain predicted from the current remembered over a time constant (0 is the current in "
              "force), on held-out blocks of time; and the drift at the unchanged setting "
              "(decision 253) re-read with that memory."),
        literature=_lit("synthesis", "washin")),
    "onoff_switches": dict(
        page="stim_optimizer", order=2,
        title="Pain around each on/off switch",
        what="Daily mean pain in windows before and after each time a side was switched on or off; descriptive.",
        literature=_lit("synthesis", "washin", "state")),
    "carry_over_ladder": dict(
        page="stim_optimizer", order=3,
        title="Up the ladder and down (carry-over)",
        what=("Pain at one current reached by a rise and by a fall within one clinic visit, everything "
              "else unchanged, from the clinic and at-home testing sheets; told apart from pain drifting "
              "over the visit by which leg came first. Also: pain rated twice at one held setting, and the "
              "settled band power of the stored titration ladders on both legs."),
        literature=_lit("synthesis", "washin")),
    "regression_to_mean": dict(
        page="stim_optimizer", order=4,
        title="Regression to the mean at one setting",
        what=("At the setting delivered most often in one rate/pulse-width group (decision 253), whether "
              "its block-to-block swing is specific to that current pair -- checked against every other "
              "way of splitting the same setting-periods, and against similar runs anywhere else in the "
              "record -- or looks like the group's own shared background pattern; descriptive, it never "
              "selects a setting."),
        literature=_lit("rtm")),
    "rating_persistence": dict(
        page="stim_optimizer", order=5,
        title="Day-to-day correlation of the pain ratings",
        what=("For each pain score: the correlation of daily mean ratings at lags 1 to 7 days, the "
              "effective number of independent days (the same lag-1 correction this project already "
              "uses for a band-power correlation) for the 0 mA stretch of 2025-07-16 to 08-22 and for "
              "all the data we have, and the next-visit protocol's 52-98 independent-day target "
              "restated as calendar days at that effective rate."),
        literature=_lit("critique", "revised_plan")),
    "stepped_current_all_bands": dict(
        page="stim_optimizer", order=6,
        title="Stepped current and bands with no plausible pain relationship",
        what=("On the stored titration-ladder points: does settled band power change with current as "
              "much in bands far from any plausible pain relationship (below 12 Hz, above 32 Hz) as in "
              "the pain-linked 21.5-27.5 Hz family, per recording route and sensing pair -- an "
              "electrical explanation of decision 229's clinic-sheet effect would predict a ratio near "
              "1, a pain-specific family a ratio well under 1."),
        literature=_lit("critique", "revised_plan")),
}
