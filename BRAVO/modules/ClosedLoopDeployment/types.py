"""Shared value types. Every result that crosses a file boundary in this module is declared here.

Kept in one place deliberately. The module is built as several estimators feeding one report, and
the failure mode for that shape is each file inventing its own near-miss of the same record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------------------------
# Device eligibility (Phase 1)
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DeviceConstraint:
    """One rule from ``percept_device_constraints.md``.

    ``severity`` is the load-bearing field. ``unknown`` means the rule EXISTS but its value has not
    been read off the programmer, and it blocks — a rule we cannot evaluate must not pass silently,
    which is the whole reason the table is data rather than a chain of ifs.
    """
    rule_id: str
    title: str
    source: str
    page: str
    severity: str                     # "blocking" | "advisory" | "unknown"
    human_text: str
    predicate: Any = None             # callable(candidate, participant) -> bool | None

    def __post_init__(self):
        if self.severity not in ("blocking", "advisory", "unknown"):
            raise ValueError(f"{self.rule_id}: severity must be blocking/advisory/unknown, "
                             f"got {self.severity!r}")


@dataclass
class EligibilityReport:
    """EVERY failure, not just the first: a clinician fixing one blocker should not have to
    re-run to discover the next."""
    eligible: bool
    failures: list = field(default_factory=list)      # [{rule_id, severity, why, page}]
    advisories: list = field(default_factory=list)
    unknowns: list = field(default_factory=list)
    #: Rows set aside because another rule already charged the SAME consideration from the SAME
    #: input — see ``constraints.RULE_DEFERS_TO``. Added 2026-09-04 as a fourth bucket rather than
    #: by deleting the duplicate row, because the observation is still worth reading; only the
    #: second charge against the verdict goes. A row lands here ONLY when its owning rule reached
    #: the same adverse verdict, so the owner is still failing and moving the row can never turn a
    #: blocked configuration into an eligible one. New field with a default, so any caller that
    #: does not know about it is unaffected.
    deferred: list = field(default_factory=list)
    checked: int = 0

    def summary(self) -> str:
        if self.eligible:
            return f"eligible ({self.checked} rules checked, {len(self.advisories)} advisory)"
        # `checked` still counts every rule in the table, and deferred rows are named separately, so
        # a reader can always reconcile the buckets against the size of the table.
        tail = f", {len(self.deferred)} deferred as duplicate" if self.deferred else ""
        return (f"NOT eligible: {len(self.failures)} blocking, {len(self.unknowns)} unknown "
                f"of {self.checked} rules checked{tail}")


# --------------------------------------------------------------------------------------------
# The three edges (Phase 2)
# --------------------------------------------------------------------------------------------
@dataclass
class EdgeEstimate:
    """One edge of the amplitude -> power -> pain triangle.

    ``cluster_unit`` is recorded on the estimate itself because the audit's central finding was that
    the wrong clustering unit inflated significance across this project; an edge that cannot say
    what it clustered on cannot be trusted downstream.
    """
    name: str                          # "E1" | "E2" | "E3"
    estimate: float | None
    ci: tuple | None
    p: float | None
    n: int
    cluster_unit: str
    n_clusters: int
    scale: str = "linear"              # linear band power unless stated
    note: str = ""
    confounded_by: list = field(default_factory=list)

    @property
    def sign(self) -> int | None:
        if self.estimate is None:
            return None
        return 0 if self.estimate == 0 else (1 if self.estimate > 0 else -1)

    @property
    def resolved(self) -> bool:
        """True only when the interval excludes zero. An estimate whose interval spans zero has not
        established a direction, and every downstream sign test must treat it as unknown."""
        if self.ci is None or self.estimate is None:
            return False
        lo, hi = self.ci
        return bool((lo > 0 and hi > 0) or (lo < 0 and hi < 0))


@dataclass
class CoherenceReport:
    """Whether the three edge signs tell a consistent story, with the uncertainty of that claim."""
    coherent: bool | None
    p_coherent: float | None           # bootstrap probability the sign pattern holds
    #: The sign patterns as DICTS, not as `str(dict)`. They used to be stringified, which put
    #: `{'E1': -1, 'E2': 1, ...}` on the wire — single-quoted keys that `JSON.parse` cannot read,
    #: with apostrophes inside the nested prose. The interface had to recover the three signs with
    #: a regular expression over a Python repr, and a serialisation change would have silently
    #: produced three absent signs rather than an error. `expected_pattern` also carries a `why`
    #: key explaining what the control law requires, so it is a mapping rather than a triple.
    expected_pattern: dict = field(default_factory=dict)
    observed_pattern: dict = field(default_factory=dict)
    n_boot: int = 0
    cluster_unit: str = ""
    note: str = ""


# --------------------------------------------------------------------------------------------
# Control authority and threshold placement
# --------------------------------------------------------------------------------------------
@dataclass
class ThresholdPlan:
    """Where the two thresholds go, and what the device will do with them."""
    upper: float | None
    lower: float | None
    scale: str = "linear"
    capture_amp_low: float | None = None
    capture_amp_high: float | None = None
    frac_time_below: float | None = None
    frac_time_between: float | None = None
    frac_time_above: float | None = None
    predicted_recapture_alert: bool | None = None
    control_authority: float | None = None
    #: Sentences that BLOCK the verdict when the pipeline runs strict: the D27 capture-artefact
    #: ceiling, and a capture whose spread cannot be measured. Since 2026-09-12 the two D26
    #: capture verdicts are NOT in here -- see ``warnings``.
    problems: list = field(default_factory=list)
    #: The two D26 capture verdicts ("inverted capture", "thresholds too close") when adverse, not
    #: yet established, or not assessed. They WARN and gate nothing: the pipeline copies them into
    #: ``DeploymentReport.warnings``, never into ``blockers``. PI decision 2026-09-12, "b and c".
    warnings: list = field(default_factory=list)
    #: The structured form of the two D26 verdicts: what each was judged on (the pooled titration
    #: slope, decision 124), its status, whether it is established, and the between-visit
    #: comparison the verdicts used to rest on, kept beside them as a number and labelled as the
    #: comparison decision 124 distrusts. Built by ``authority.d26_capture_verdicts``.
    capture_verdicts: dict = field(default_factory=dict)
    note: str = ""


@dataclass
class ReplayResult:
    """What the Dual Threshold controller would have done on an observed power series."""
    t_s: list = field(default_factory=list)
    amplitude_mA: list = field(default_factory=list)
    state: list = field(default_factory=list)          # "below" | "between" | "above"
    frac_time_at_upper: float | None = None
    frac_time_at_lower: float | None = None
    #: The LONGEST CONTINUOUS excursion at each limit, in seconds — not the total. A clinician
    #: asked to approve a configuration wants to know how long a single stretch at the upper limit
    #: could last, and a total fraction cannot answer that: 10% of a day at the upper limit is one
    #: two-and-a-half-hour block or a hundred ninety-second blips, and those are different things to
    #: consent to. This is also the closest the Percept comes to a duty limiter, because cycling is
    #: NOT available in a group with Adaptive Therapy (A610 p. 35, encoded as D32) and no maximum
    #: duration or dwell limit appears anywhere in the supplied device documents.
    longest_run_at_upper_s: float | None = None
    longest_run_at_lower_s: float | None = None
    n_transitions: int = 0
    saturated: bool | None = None
    params: dict = field(default_factory=dict)
    note: str = ""


# --------------------------------------------------------------------------------------------
# Protocol generation (code buildable now; its CONCLUSIONS need prospective data)
# --------------------------------------------------------------------------------------------
@dataclass
class Protocol:
    steps: list = field(default_factory=list)          # ordered list of dicts
    n_pairs: int = 0
    alpha: float = 0.05
    power: float | None = None
    detectable_d: float | None = None
    duration_min: float | None = None
    seed: int | None = None
    note: str = ""


# --------------------------------------------------------------------------------------------
# The report the interface reads
# --------------------------------------------------------------------------------------------
@dataclass
class DeploymentReport:
    participant: str
    eligibility: EligibilityReport | None = None
    edges: dict = field(default_factory=dict)          # {"E1": EdgeEstimate, ...}
    #: The estimate an edge REPLACED, kept for the record: since 2026-09-11 E1 is the pooled
    #: titration slope when one is stored, and the historical setting-epoch slope lands here.
    edges_historical: dict = field(default_factory=dict)
    coherence: CoherenceReport | None = None
    threshold: ThresholdPlan | None = None
    replay: ReplayResult | None = None
    protocol: Protocol | None = None
    #: The programmable device parameters and the predicted duty cycle, from prescription.py.
    #: Added 2026-09-04 as a new field with a default, so any caller that predates it is
    #: unaffected. This is the module's ANSWER rather than its evidence: everything above decides
    #: whether a configuration may be used, and this says what to type into the programmer.
    prescription: Any = None
    #: Every threshold mode's prescription plus the recommended mode, from
    #: ``prescription.prescribe_all_modes``. Separate from ``prescription`` because the mode a
    #: clinician is EXPLORING and the mode this module RECOMMENDS are different things, and
    #: collapsing them would make the toggle silently snap back to the recommendation.
    prescriptions: Any = None
    candidates: Any = None
    blockers: list = field(default_factory=list)
    #: WARNINGS GATE NOTHING. Sentences a reader should see beside the verdict that do not enter
    #: ``is_licensed``: today the two D26 capture verdicts (``ThresholdPlan.warnings``). Added
    #: 2026-09-12 as a new field with a default, so a caller that predates it is unaffected, and
    #: mirroring decision 104, which made the reliable-change check a warning that blocks nothing.
    #: Serialised by ``adapter.report_to_dict`` as ``verdict_detail.warnings``.
    warnings: list = field(default_factory=list)
    manifest: dict = field(default_factory=dict)

    def is_licensed(self) -> bool:
        """The single boolean the interface reads.

        Deliberately conjunctive and deliberately pessimistic: device-eligible AND every edge
        resolved AND the sign pattern coherent AND no blocker. Anything unmeasured reads as not
        licensed, because the alternative — treating absence of evidence as permission — is the
        failure this module exists to prevent.

        ``warnings`` IS NOT READ HERE, on purpose. PI decision 2026-09-12, his words "b and c":
        the two D26 capture checks (inverted capture, thresholds too close) warn rather than block.
        Two reasons. A wrong-way loop is caught by the device's own inverted-capture alert at the
        programming visit, so the module's prediction of it is a heads-up and not the last line of
        defence. And the quantity those two verdicts now read -- the pooled titration slope, E1 --
        already gates through "every edge resolved" above: a slope whose interval spans zero leaves
        E1 unresolved and the report unlicensed, so a second block from the same number would be
        the same fact charged twice.
        """
        if self.blockers:
            return False
        if self.eligibility is None or not self.eligibility.eligible:
            return False
        if not self.edges or not all(e.resolved for e in self.edges.values()):
            return False
        return bool(self.coherence is not None and self.coherence.coherent)
