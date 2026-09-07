"""A single canonical form for decoded Percept recordings, built once and read many times.

This package is a MEASURED PROTOTYPE, not a platform change. Nothing in the running
platform imports it; it exists so the saving a shared decoded form would buy can be
measured against the current code on live recordings, and so the measurement can be
repeated by anyone who doubts it.

Read `representation.py` for what the form holds and in what units, and
`per_pro_lsb_indexed.py` for the one consumer built against it.
"""

from .representation import (                                    # noqa: F401
    CHANNEL_INDEX_VERSION,
    ChannelIndex,
    build_channel_index,
)
from .per_pro_lsb_indexed import per_pro_lsb_indexed             # noqa: F401
