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
    expected_pattern: str = ""
    observed_pattern: str = ""
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
    problems: list = field(default_factory=list)
    note: str = ""


@dataclass
class ReplayResult:
    """What the Dual Threshold controller would have done on an observed power series."""
    t_s: list = field(default_factory=list)
    amplitude_mA: list = field(default_factory=list)
    state: list = field(default_factory=list)          # "below" | "between" | "above"
    frac_time_at_upper: float | None = None
    frac_time_at_lower: float | None = None
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
    manifest: dict = field(default_factory=dict)

    def is_licensed(self) -> bool:
        """The single boolean the interface reads.

        Deliberately conjunctive and deliberately pessimistic: device-eligible AND every edge
        resolved AND the sign pattern coherent AND no blocker. Anything unmeasured reads as not
        licensed, because the alternative — treating absence of evidence as permission — is the
        failure this module exists to prevent.
        """
        if self.blockers:
            return False
        if self.eligibility is None or not self.eligibility.eligible:
            return False
        if not self.edges or not all(e.resolved for e in self.edges.values()):
            return False
        return bool(self.coherence is not None and self.coherence.coherent)
