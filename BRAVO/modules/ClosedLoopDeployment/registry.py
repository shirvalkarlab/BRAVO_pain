"""Phase 3: an append-only pre-registration ledger.

This file can conclude nothing. It exists so that the prospective phases CAN conclude something.

The problem it solves is specific and has already occurred in this project. The historical record
was scanned across 50 configurations and 18 bands, candidates were ranked, and the ranking then
informed which analyses were run and reported. Once that has happened, a p-value computed on the
same data no longer means what it appears to mean, because the hypothesis was chosen after seeing
the answer. The only repair is to fix the hypothesis, the estimator, the alpha level and the
stopping rule BEFORE the next dataset exists, and to make the record of that commitment tamper
evident.

Hence append-only with a content hash. Amendments are permitted, because a plan that cannot be
corrected is a plan that gets quietly ignored — but an amendment is a new dated entry that names
what changed and why, never an edit to a previous one. A reader can therefore always reconstruct
what was committed to before the data arrived, which is the only thing that matters for inference.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(entries):
    """Hash of the whole chain, so a silent edit to an earlier entry is detectable."""
    return hashlib.sha256(json.dumps(entries, sort_keys=True, default=str).encode()).hexdigest()[:16]


class Registry:
    """A dated, append-only list of registration entries backed by one JSON file."""

    def __init__(self, path):
        self.path = Path(path)
        self.entries = []
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self.entries = data.get("entries", [])
            recorded = data.get("digest")
            if recorded and recorded != _digest(self.entries):
                # Report rather than raise: a tampered ledger is a finding the caller must see, and
                # refusing to load it would make the tampering harder to inspect, not easier.
                self.tampered = True
            else:
                self.tampered = False
        else:
            self.tampered = False

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"entries": self.entries, "digest": _digest(self.entries)}, indent=2, default=str))

    def register(self, *, candidates, estimators, alpha, correction, stopping_rule,
                 primary_outcome, notes=""):
        """Commit a pre-registration. Refuses to overwrite; use ``amend`` to change something."""
        entry = {"kind": "registration", "at": _now(), "candidates": list(candidates),
                 "estimators": dict(estimators), "alpha": float(alpha),
                 "correction": correction, "stopping_rule": stopping_rule,
                 "primary_outcome": primary_outcome, "notes": notes}
        self.entries.append(entry)
        self._save()
        return entry

    def amend(self, *, what_changed, why, fields=None):
        """Record a change as a NEW entry. The prior entry is never modified.

        ``why`` is required and must be non-empty: an amendment without a stated reason is
        indistinguishable from moving the goalposts, which is the exact failure this ledger exists
        to make visible.
        """
        if not str(why).strip():
            raise ValueError("an amendment must state why; an unexplained amendment is "
                             "indistinguishable from changing the hypothesis to fit the data")
        if not self.entries:
            raise ValueError("nothing registered yet; call register() before amending")
        entry = {"kind": "amendment", "at": _now(), "what_changed": what_changed,
                 "why": why, "fields": dict(fields or {})}
        self.entries.append(entry)
        self._save()
        return entry

    def effective(self):
        """The current plan: the registration with every amendment's fields applied in order."""
        reg = next((e for e in self.entries if e["kind"] == "registration"), None)
        if reg is None:
            return None
        out = dict(reg)
        applied = []
        for e in self.entries:
            if e["kind"] == "amendment":
                out.update(e.get("fields") or {})
                applied.append({"at": e["at"], "what_changed": e["what_changed"], "why": e["why"]})
        out["amendments_applied"] = applied
        out["registered_at"] = reg["at"]
        out["digest"] = _digest(self.entries)
        out["tampered"] = self.tampered
        return out
