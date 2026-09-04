"""Closed-loop deployment: is there a control signal, and may it be programmed.

A separate module from ``modules.Biomarkers`` because the estimands, the units and the audience all
differ, and because the biomarker module's outputs are this module's INPUTS. Biomarkers asks whether
a band tracks pain. This module asks whether that band can drive a device — a question the two were
shown to answer almost independently (rank correlation 0.008 across 558 band-cells on RCS08), which
is exactly why merging them would hide the disagreement worth seeing.

Read ``types.py`` first: every cross-file value is a dataclass declared there.
"""
