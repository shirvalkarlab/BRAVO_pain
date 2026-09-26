"""A single canonical form for decoded Percept recordings, built once and read many times.

`representation` — the form: decoded recordings grouped by canonical channel name, in the
units they were decoded in, with no pain report and no calibration constant anywhere in it.
`matching` — the shared matcher every reader of the form pairs samples to reports with.

This package started as a measured prototype that nothing imported (tracked in `14ad802`). Track
B step 1 made it real code: its tests run on both runners, and both import spellings resolve to
one module object. Its first reader, `per_pro_lsb_indexed` (one band-power value per pain report),
was deleted on 2026-09-21 with the platform function it served (decision 224).
`sensing_rule` — the device's sensing-pair rule (decision 217), the one home the Stim Optimizer, the
Closed-Loop page and the Biomarkers heat maps read (2026-09-26); registered under both spellings
below so its functions are one object whichever spelling a caller used.
"""
import sys as _sys

from . import import_alias, representation, sensing_rule   # noqa: F401
from .representation import (                                    # noqa: F401
    CHANNEL_INDEX_VERSION,
    ChannelIndex,
    build_channel_index,
)

__all__ = ["CHANNEL_INDEX_VERSION", "ChannelIndex", "build_channel_index", "representation",
           "sensing_rule"]

# ONE MODULE OBJECT UNDER BOTH SPELLINGS, for the same reason as `CacheStore/__init__.py`: the
# container imports this package as `modules.DecodeCommon` and the host suite as `DecodeCommon`.
_OTHER = "DecodeCommon" if __name__ == "modules.DecodeCommon" else "modules.DecodeCommon"
for _name, _mod in (("", _sys.modules[__name__]), (".representation", representation),
                    (".import_alias", import_alias), (".sensing_rule", sensing_rule)):
    _sys.modules.setdefault(_OTHER + _name, _mod)
