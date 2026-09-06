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
