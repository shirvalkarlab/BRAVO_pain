"""Closed-loop deployment: is there a control signal, and may it be programmed.

A separate module from ``modules.Biomarkers`` because the estimands, the units and the audience all
differ, and because the biomarker module's outputs are this module's INPUTS. Biomarkers asks whether
a band tracks pain. This module asks whether that band can drive a device — a question the two were
shown to answer almost independently (rank correlation 0.008 across 558 band-cells on RCS08), which
is exactly why merging them would hide the disagreement worth seeing.

Read ``types.py`` first: every cross-file value is a dataclass declared there.
"""

# ONE MODULE OBJECT UNDER BOTH IMPORT SPELLINGS (`modules.ClosedLoopDeployment` in the container, `ClosedLoopDeployment` on the
# host suite). Without this, a process with both roots on the path -- every gunicorn worker --
# loads two copies of every submodule: two sets of in-process memos and two copies of every
# module-level switch (review C4, 2026-09-12; decision 143). `DecodeCommon.import_alias` says how.
try:
    from modules.DecodeCommon.import_alias import alias_both_spellings as _alias_both_spellings
except ImportError:                                   # the host suite's root
    from DecodeCommon.import_alias import alias_both_spellings as _alias_both_spellings
_alias_both_spellings(__name__)
del _alias_both_spellings
