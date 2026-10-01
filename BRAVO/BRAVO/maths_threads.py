"""One maths-library thread by default for every BRAVO process (speed-up item A2, 2026-10-01).

Imported first thing by `BRAVO/settings.py`, before anything loads numpy, so web workers,
management commands and the bridge all read it. Without it each worker starts as many BLAS/OpenMP
threads as the machine has cores (16 on the Mac, 64 on the Jetstream2 BRAVO) for every small fit,
and the workers then contend for the cores: decisions 140 and 268 measured small fits 10-15x slower
that way, with every value identical. Proof on RCS08: the heat-map grid, the Closed-Loop report and
the Stim Optimizer two-stage request change in timing fields only (43,685 / 73,600 / 64,212 fields).

`setdefault`, so a value already in the environment wins.
Test: modules/DecodeCommon/tests/test_blas_threads_default.py.
"""
import os

VARS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")

for _var in VARS:
    os.environ.setdefault(_var, "1")
