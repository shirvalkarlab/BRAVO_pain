'One maths-library thread by default for every BRAVO process (speed-up item A2, 2026-10-01).'
import os

VARS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")

for _var in VARS:
    os.environ.setdefault(_var, "1")
