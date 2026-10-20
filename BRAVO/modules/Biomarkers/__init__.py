"""
Biomarkers module: runs the dbs_stage2_percept pain-biomarker routines on BRAVO's decoded
Percept recordings, aligned to REDCap PROs.

Layout:
  routines/streaming_psd.py   -- biomarker science, extracted from dbs_stage2 notebooks (unchanged)
  routines/redcap_client.py   -- REDCap PRO pull (vendored; token via env var)
  adapter.py                  -- the only glue: BRAVO recording <-> routine I/O, PRO alignment
  pipeline.py                 -- one-patient library-mode runner -> flat file

Library mode only for now (no Django endpoint, no React); see pipeline.py for deferred hooks.
"""

# ONE MODULE OBJECT UNDER BOTH IMPORT SPELLINGS (`modules.Biomarkers` in the container, `Biomarkers` on the
# host suite). Without this, a process with both roots on the path -- every gunicorn worker --
# loads two copies of every submodule: two sets of in-process memos and two copies of every
# module-level switch (review C4, 2026-09-12; decision 143). `DecodeCommon.import_alias` says how.
try:
    from modules.DecodeCommon.import_alias import alias_both_spellings as _alias_both_spellings
except ImportError:                                   # the host suite's root
    from DecodeCommon.import_alias import alias_both_spellings as _alias_both_spellings
_alias_both_spellings(__name__)
del _alias_both_spellings
