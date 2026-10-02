# Blinded, randomised in-clinic comparison: RL model's setting against the home setting (RCS08)

Pre-registered 2026-10-02, before any rating. Approved by the PI the same day ("Yes, please run the
small blinded randomized in clinic comparison!"), and the test setting chosen by him from the
options offered. Nothing in BRAVO writes to the device; a clinician programs every step by hand.
Code: `BRAVO/modules/StimRL/clinic_comparison.py` (tests: `tests/test_clinic_comparison.py`).

## Question

At the patient's current contact, does the RL model's setting lower overall pain within minutes
compared with the home setting, when neither the patient nor the rater knows which is on?

## Settings

| | rate | Left current | Right current | Left width | Right width | contacts |
|---|---|---|---|---|---|---|
| HOME (C) | 55 Hz | 3.0 mA | 2.5 mA | 100 µs | 150 µs | L C+2- (Left 2a-2b-2c / Right 1a-1b-1c-2a-2b-2c) |
| TEST (R) | 55 Hz | 3.5 mA | 3.0 mA | 100 µs | 150 µs | same |

- **HOME:** in force since 2026-09-02 19:15 UTC, according to the long-term record. The programmer
  confirms it on the tablet before step 1 and stops if it differs.
- **TEST:** the Q-table actor-critic's pick (delta reward, exploit reading) for L C+2- from today's
  state. It is the home setting of 2026-08-12 to 09-02.
  - It is within the 4.5 mA ceiling and the device range, a check that can refuse it
    (`check_settings`).
  - It has been given before: 43 rated steps at 3.5 mA or more Left and 3.0 mA or more Right at
    55 Hz, over 8 visits up to 2026-09-24. Side effects were graded 7 times: none in 4, mild in 3,
    never moderate.
  - The reason for the 2026-09-02 step down is not in the record.
- **The model's own prediction, R minus C:** -0.09 points, about no difference. So this visit
  tests whether a 0.5 mA increase on each side matters acutely. It is a weak test of the RL
  method itself (REPORT.md, Section 1).

## Design

- **Steps:** 8 pairs, 16 steps. Each pair holds one TEST and one HOME step. The order within each
  pair was drawn from the operating system's random source and sealed in `allocation.json`.
  - SHA-256: `9d465d0c9ffec061d58d34d820119b2e9d3920ab79bac625b762bd68ba4db1b3`.
  - The file is gitignored, in `BRAVO/_agent_bridge/_stim_rl_data/clinic_comparison/`.
- **Timing:** each step lasts 3 minutes, and ratings are taken in its last 30 seconds. Past sheet
  steps have a median of 60 s, and three-quarters last 2 minutes or less. After each TEST step,
  2 minutes at HOME. About 64 minutes in all.
- **Blinding:**
  - The programmer holds `programmer_sheet.xlsx`. The rater holds `rater_sheet.xlsx`, which names
    no setting (checked by a test).
  - At every step change the programmer opens the program screen and confirms a value, so the
    patient cannot tell from the programmer's actions.
  - The PI should not see the programmer sheet if he is in the room or rating.
- **Outcome:**
  - Primary: overall pain, 0-10.
  - Secondary: left leg and back pain, 0-10, and side-effect grade.

## Analysis (fixed now)

- **Per pair:** TEST minus HOME rating; negative means TEST hurt less.
- **Primary test:** exact one-sided sign-flip test over all 256 sign patterns, so the smallest
  possible p is 1/256.
- **Pre-registered rule:** TEST is better if p < 0.05. The mean difference is reported with its
  95% interval.
- **Missing ratings:** a pair missing either rating is dropped and listed.
- **Power:** past repeat ratings at an unchanged setting move with a spread of 0.70 points (90
  pairs). Under the rule, 8 pairs give about 0.97 power for a 1-point drop, 0.56 for 0.5 points,
  and a 0.045 false-positive rate (4,000 simulations).
- **Command:** `python -m StimRL.clinic_comparison analyze <filled rater_sheet.xlsx>`.

## Stop rules

- A mild-persistent side effect during TEST: return to HOME, mark the pair, continue.
- A moderate or severe side effect: return to HOME and end the session.
- The patient asks to stop: end.
- TEST rated 2 or more points worse than HOME in two pairs in a row: stop the TEST steps.

## What a result will and will not mean

- **One visit day establishes nothing on its own.**
- **If p < 0.05:** a 0.5 mA increase lowered acute pain under blinding at this visit. Repeat it
  at a second visit before any change to the home setting.
- **If p >= 0.05:** no difference was detectable over the range tested. State the interval. Never
  say the setting has no effect.
- **Either way:** this does not validate the RL models, which predicted no difference.
