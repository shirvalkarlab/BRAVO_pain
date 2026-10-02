"""Fixed numbers for the offline RL study, each with where it comes from.

Nothing here is new clinical policy: every limit is copied from the module that owns it, and a
test (`tests/test_data_pipeline.py`, the last four) reads the owning file and fails if the two disagree.
"""

# ---- Safety limits ----------------------------------------------------------------------------
#: Highest current allowed on either side, mA. The PI's stated ceiling for RCS08 (2026-09-14),
#: `StimOptimizer/safety_ceiling.py` PI_STATED_CEILING_MA.
AMP_CEILING_MA = 4.5
#: Current at which the "close to the ceiling" penalty starts, mA. A study choice, not a clinical
#: limit: the last 0.5 mA below the ceiling, one ordinary programming step of 0.5 mA.
AMP_WARN_MA = 4.0
#: Top of the current range the policy may output, mA: the Stim Optimizer's search-grid top
#: (`StimOptimizer/routines/objective.py` AMP_HARD_LIMIT_MA). Above the ceiling on purpose, so a
#: policy that pushes past 4.5 mA shows it in its risk score instead of being hidden by the range.
AMP_ACTION_MAX_MA = 5.0
#: Side-effect ladder on the visit sheets: 0 none, 1 mild, 2 mild-persistent, 3 moderate,
#: 4 severe. Cost in pain points per `StimOptimizer/routines/objective.py` (decision 165);
#: moderate or worse is never acceptable (SE_THRESHOLD = 3, decision 164).
SIDE_EFFECT_COST = {0: 0.0, 1: 1.0, 2: 2.0}
SIDE_EFFECT_TERMINAL_AT = 3
#: Device envelope (`ClosedLoopDeployment/constraints.py` GENERAL_ENVELOPE).
DEVICE_RATE_HZ = (2.0, 250.0)
DEVICE_PW_US = (20.0, 450.0)

# ---- Action space: [rate, Left current, Right current, Left pulse width, Right pulse width] -----
ACTION_NAMES = ("freq_hz", "amp_mA_Left", "amp_mA_Right", "pw_us_Left", "pw_us_Right")
#: Range each action dimension is scaled into [-1, 1] over. Rate and pulse width span what the
#: visit sheets and the long-term settings actually delivered (10-180 Hz, 40-290 us), so the
#: policy cannot propose a rate or width no one has ever tried on this patient.
ACTION_LOW = (10.0, 0.0, 0.0, 40.0, 40.0)
ACTION_HIGH = (180.0, AMP_ACTION_MAX_MA, AMP_ACTION_MAX_MA, 290.0, 290.0)

# ---- Penalties, in pain points (the 0-10 sheet scale) ------------------------------------------
#: Reward on a step that breaks a safety limit; the episode ends there.
TERMINAL_PENALTY = -10.0
#: Largest penalty for sitting between AMP_WARN_MA and the ceiling (rises linearly from 0).
PROXIMITY_PENALTY = 2.0

# ---- State ---------------------------------------------------------------------------------------
#: Pain sites on the visit sheets, 0-10, higher is worse (`StimOptimizer/clinic_pain.PAIN_FIELDS`).
PAIN_SITES = ("overall", "head", "back", "left_leg", "left_foot", "right_leg", "right_foot")
#: Left contacts the policy conditions on (clinic-sheet notation, `stage1_openloop.left_contact_label`).
#: Every other label is "other". The policy recommends rate, current and width FOR a contact; it
#: never pools two contacts' effects into one recommendation (decision 74).
CONTACT_LEVELS = ("L C+2-", "L C+1-", "off (Left 0 mA)", "L 1+2-", "L C+2a-")

# ---- Long-term (chronic) validation --------------------------------------------------------------
#: REDCap items and how each maps onto the 0-10 sheet scale (higher = worse). Relief is reversed.
REDCAP_TO_POINTS = {
    "nrs": lambda x: x,
    "vas": lambda x: x / 10.0,
    "left_leg_vas": lambda x: x / 10.0,
    "back_vas": lambda x: x / 10.0,
    "mpq_sum": lambda x: x * 10.0 / 45.0,      # normaliser 45 as in StimOptimizer
    "relief": lambda x: 10.0 - x / 10.0,
}
#: A report counts toward a setting period only after this many minutes in it (the adapter's
#: `attach_pros` wash-in, 1 min).
WASHIN_MIN = 1.0
#: Setting periods with fewer reports than this are left out of validation.
MIN_REPORTS_PER_EPOCH = 3
