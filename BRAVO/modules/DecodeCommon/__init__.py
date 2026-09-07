"""A single canonical form for decoded Percept recordings, built once and read many times.

`representation` — the form: decoded recordings grouped by canonical channel name, in the
units they were decoded in, with no pain report and no calibration constant anywhere in it.
`per_pro_lsb_indexed` — one band-power value per pain report, read out of the form by the same
three-tier rule as `Biomarkers.routines.availability.per_pro_lsb`.

This package started as a measured prototype that nothing imported (tracked in `14ad802`). Track
B step 1 made it real code: its tests run on both runners, and both import spellings resolve to
one module object. Adopting it at the request's hottest line is Track B step 2; until that step
lands, the running server still uses `availability.per_pro_lsb` alone.
"""
import sys as _sys

from . import per_pro_lsb_indexed as _consumer, representation   # noqa: F401
from .representation import (                                    # noqa: F401
    CHANNEL_INDEX_VERSION,
    ChannelIndex,
    build_channel_index,
)
from .per_pro_lsb_indexed import per_pro_lsb_indexed             # noqa: F401

__all__ = ["CHANNEL_INDEX_VERSION", "ChannelIndex", "build_channel_index",
           "per_pro_lsb_indexed", "representation"]

# ONE MODULE OBJECT UNDER BOTH SPELLINGS, for the same reason as `CacheStore/__init__.py`: the
# container imports this package as `modules.DecodeCommon` and the host suite as `DecodeCommon`.
_OTHER = "DecodeCommon" if __name__ == "modules.DecodeCommon" else "modules.DecodeCommon"
for _name, _mod in (("", _sys.modules[__name__]), (".representation", representation),
                    (".per_pro_lsb_indexed", _consumer)):
    _sys.modules.setdefault(_OTHER + _name, _mod)
