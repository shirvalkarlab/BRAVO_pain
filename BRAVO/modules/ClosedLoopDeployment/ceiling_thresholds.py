"""WHY THIS EXISTS. Decision 33 requires a per-channel ceiling on the device's own reported band
power, because about 1 percent of simultaneous windows are device-side spikes and a rule that
accepts the device's raw reading unconditionally adopts those spikes as truth. The first
implementation computed the ceiling as 10 times the SAME 30-second window's own median, which has
a real weakness: a window that is mostly bad readings inflates its own median, so the check can
miss exactly the case that matters most (this is the statistical "masking" problem -- see the
outlier-literature review this replaces, 2026-09-08). These tables fix that by computing the
ceiling from a period of data separate from the window being checked: every historical reading
this participant has ever produced for that exact (electrode, band centre) pair, not the window
under test.

HOW THESE NUMBERS WERE COMPUTED, so they can be reproduced or extended. For each group, take the
99.5th percentile of every historical raw value (excluding the known device error code
4294967295, which is 2 to the 32nd power minus 1 and not a real reading) and use it as the
ceiling: a value above it is treated as a device-side spike. A group whose entire history is
exactly zero (the device never actively reported on that combination) is left out of the table
entirely rather than given a ceiling of zero, since a zero ceiling would flag every future nonzero
reading as a spike -- 0 of 582 time-domain groups, 0 of 582 raw-LSB groups
and 4 of 32 power-domain groups were degenerate this way and are absent from their
tables. A group with no entry at all means there is no historical basis to judge it, and the
ceiling check simply does not run for that combination -- it is never treated as a reason to
refuse the window.

ONLY `POWER_DOMAIN_CEILINGS` IS WIRED IN, replacing `DEVICE_SPIKE_FOLD` in
`three_source_response.settled_device_band_power` (decision 52). `TIME_DOMAIN_CEILINGS` and
`RAW_LSB_CEILINGS` are built for the same purpose applied to the two tile-cache families
(`td_transform` and `psd_bridge` in `Biomarkers.routines.availability.raw_lsb_spectrum_cache`) but
are not yet consumed anywhere -- wiring them into the tile-building path is a separate decision,
since that path feeds every module and any change to it needs its own equality proof.

Keys are (electrode, band centre in Hz). Recomputing these tables means re-running the export
script against the live record and replacing this file; they are not meant to be hand-edited."""

PERCENTILE = 99.5

TIME_DOMAIN_CEILINGS = {}  # Participant-specific values remain in private reviewed storage.

RAW_LSB_CEILINGS = {}  # Participant-specific values remain in private reviewed storage.

POWER_DOMAIN_CEILINGS = {}  # Participant-specific values remain in private reviewed storage.

# Aditya canonical compatibility imports/constants.



# Retained active Aditya interfaces.
