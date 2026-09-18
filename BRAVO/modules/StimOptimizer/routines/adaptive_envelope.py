"""The adaptive envelope: the settings the device's Adaptive Therapy (closed-loop) mode can use.

WHY THIS MODULE EXISTS
----------------------
The principal investigator's instruction, 2026-09-12, verbatim: "don't recommend settings that
adaptive cannot use unless there is a scientific or physiological reason."

THE OVERRIDE
------------
The instruction carries its own exception: a scientific or physiological reason to explore outside
the envelope. ``Constraint.lifted`` is True only when a NON-EMPTY reason is recorded, and the reason
and the name of who gave it travel with the frozen configuration. A request that names the override
key without a reason is treated as no override at all, and the report says the override was ignored
and why, so an empty override can never silently disable the constraint."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import percept_adaptive as PA

#: The adaptive minimum rate. ONE definition, shared with the gate through ``percept_adaptive``.
MIN_RATE_HZ = float(PA.MIN_ADAPTIVE_RATE_HZ)

#: The adaptive ceilings. Not published in the labelling and not found in the device record, so
#: not known and not enforced. See the module docstring.
MAX_RATE_HZ = None
MAX_PW_US = None

#: Where the numbers come from, carried onto the report so a reader can tell a quoted value from a
#: PI-stated one.
SOURCE = ("minimum rate 55 Hz: PI-stated, StimOptimizer/routines/percept_adaptive.py "
          "MIN_ADAPTIVE_RATE_HZ (the A610 Clinician Programming Guide p. 35 states the minimum is "
          "higher with Adaptive Therapy without printing the number); the adaptive rate and "
          "pulse-width ceilings are not published and are not enforced")


@dataclass(frozen=True)
class Constraint:
    """Whether the envelope is applied to a search, and if it is lifted, by whom and why.

    ``requested`` records that an override was ASKED for, whether or not it carried a reason; the
    two are separated so the report can say "an override without a reason was ignored" rather than
    silently treating it as absent.
    """

    min_rate_hz: float = MIN_RATE_HZ
    reason: str | None = None
    by: str | None = None
    requested: bool = False

    @property
    def lifted(self) -> bool:
        """True only when a non-empty reason was given: the constraint is then NOT applied."""
        return bool(self.reason and str(self.reason).strip())

    @property
    def ignored_note(self) -> str | None:
        """The sentence for an override that was asked for with no reason, else ``None``."""
        if self.requested and not self.lifted:
            return ("an override to explore outside the adaptive envelope was supplied without a "
                    "reason and was IGNORED: the constraint stays. An override with no reason is "
                    "indistinguishable from disabling the check; a scientific or physiological "
                    "reason must be stated for the search to consider settings adaptive cannot use")
        return None

    def statement(self) -> str:
        """The provenance sentence the frozen configuration carries."""
        if self.lifted:
            who = f" by {self.by}" if self.by else ""
            return (f"explored outside the adaptive envelope for the stated reason{who}: "
                    f"{str(self.reason).strip()}")
        return (f"constrained to the adaptive envelope (rate >= {self.min_rate_hz:g} Hz, the "
                "device's adaptive minimum; the adaptive rate and pulse-width ceilings are not "
                "published and are not enforced)")


def make_constraint(*, reason=None, by=None, requested=None, min_rate_hz=MIN_RATE_HZ) -> Constraint:
    """Build a :class:`Constraint` from a caller's override fields.

    ``requested`` defaults to "a reason argument was passed at all" (``reason is not None``), so
    an empty string counts as requested-but-empty and is reported as ignored.
    """
    r = None if reason is None else str(reason).strip()
    req = (reason is not None) if requested is None else bool(requested)
    return Constraint(min_rate_hz=float(min_rate_hz), reason=(r or None),
                      by=(str(by).strip() if by else None), requested=req)


def rate_in_envelope(rate_hz, *, min_rate_hz=MIN_RATE_HZ) -> bool:
    """Is this rate one the adaptive mode can be programmed with?"""
    try:
        r = float(rate_hz)
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(r) and r >= float(min_rate_hz))


def grid_mask(grid, *, min_rate_hz=MIN_RATE_HZ) -> np.ndarray:
    """Boolean mask over ``grid.grid_X()`` rows: True where the cell's rate is in the envelope.

    ``grid`` is ``routines/surrogate.ParameterGrid``; column 0 of ``grid_X()`` is the rate.
    """
    gx = np.asarray(grid.grid_X(), float)
    return gx[:, 0] >= float(min_rate_hz)


def rates_excluded_from_grid(grid, *, min_rate_hz=MIN_RATE_HZ) -> list:
    """The distinct rates on the candidate grid that the envelope excludes, ascending."""
    freqs = np.asarray(getattr(grid, "freqs", np.unique(np.asarray(grid.grid_X(), float)[:, 0])),
                       float)
    return [float(f) for f in sorted(freqs) if f < float(min_rate_hz)]


def exclusion_reason(rate_hz, *, min_rate_hz=MIN_RATE_HZ) -> str:
    """The one-line reason a rate is outside the envelope, in the words the report uses."""
    return f"{float(rate_hz):g} Hz excluded: below the {float(min_rate_hz):g} Hz adaptive minimum"


def brainsense_pair_demonstrated(rate_hz, pw_us, hemisphere) -> dict:
    """REPORTING ONLY: has this exact (rate, pulse width) been accepted by the device in a
    BrainSense group on this side, according to ``ClosedLoopDeployment/device_facts``?

    Returns ``{"demonstrated": True | False | None, "note": str}``. ``False`` means the pair has
    not been seen in the record, which is weaker than forbidden and is said so; ``None`` means the
    question could not be asked (the table could not be read, or an input is missing).
    """
    try:
        try:
            from modules.ClosedLoopDeployment import device_facts as _df
        except ImportError:
            from modules.ClosedLoopDeployment import device_facts as _df
    except Exception as exc:                          # noqa: BLE001 -- reporting only
        return {"demonstrated": None,
                "note": ("not checked: the device-facts table could not be read "
                         f"({type(exc).__name__}: {exc})")}
    try:
        seen = _df.brainsense_pair_programmed(rate_hz, pw_us, hemisphere)
    except Exception as exc:                          # noqa: BLE001 -- reporting only
        return {"demonstrated": None,
                "note": f"not checked: {type(exc).__name__}: {exc}"}
    prov = str(getattr(_df, "BRAINSENSE_PAIRS_PROVENANCE", ""))
    if seen is None:
        return {"demonstrated": None,
                "note": ("not checked: rate, pulse width or hemisphere missing, or the hemisphere "
                         "is not in the device-facts table")}
    if seen:
        return {"demonstrated": True,
                "note": (f"{float(rate_hz):g} Hz at {float(pw_us):g} us has been programmed in a "
                         f"BrainSense group on the {hemisphere} side ({prov})")}
    return {"demonstrated": False,
            "note": (f"{float(rate_hz):g} Hz at {float(pw_us):g} us has NOT been seen in a "
                     f"BrainSense group on the {hemisphere} side ({prov}). This is not a device "
                     "prohibition: the pair has not been demonstrated here, which is weaker than "
                     "forbidden")}
