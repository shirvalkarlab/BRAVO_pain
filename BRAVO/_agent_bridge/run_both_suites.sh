#!/bin/sh
# Both test suites at once, in one bridge job, on the container's 16 cores. Each writes its own
# log; the summary lines are printed together at the end.
#
# Usage (from the repository root on the host):
#   python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 5 "sh _agent_bridge/run_both_suites.sh"
#   python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 5 "sh _agent_bridge/run_both_suites.sh --live"
# then poll BRAVO/_agent_bridge/outbox/<job>.out.
#
# THE ROUTINE RUN (no argument), since 2026-09-12, is three passes:
#   1. host, across 8 cores (pytest-xdist): every host test not marked `store` or `live`;
#   2. host, serially: the `store` tests -- the ones that read or write the production cache store
#      or the live database, which must never run in parallel with each other or with pass 1;
#   3. container (`run_tests.py`): the Biomarkers, CacheStore and DecodeCommon tests, with the
#      `live` ones skipped and counted.
# Passes 1 and 3 run side by side; pass 2 runs after pass 1 on the host.
#
# THE LIVE RUN (`--live`) runs ONLY the tests marked `live` -- the ones that read the live RCS08
# record -- on both runners, serially. The daily pass (`stability_precompute_loop.sh`) calls it, so
# they still run every day; they just no longer cost every routine run 50-odd seconds.
#
# The markers are declared in modules/pytest.ini. The container runner reads the same `live` mark
# off each test function (`pytestmark`), so both runners agree on which tests are live.
#
# BLAS THREADS ARE CAPPED IN THE PARALLEL PASS, and that cap is most of the speed-up. Measured
# 2026-09-12: the parallel pass with 8 workers each left on the default 16 BLAS threads took 104 s,
# SLOWER than the 94 s serial run, because 128 threads spun on 16 cores; with 2 threads per worker
# the same pass took 9.8 s, and every Stage 1 fit that had cost 3-5 s cost 0.5 s. The serial store
# pass and the container runner keep the default thread count, so the numbers they produce are
# computed under the same BLAS settings as production.
# EVERY CORE (2026-10-02, the PI: "run them massively parallel"). The cores are shared out: three
# quarters to the host pass (pytest-xdist, `--dist worksteal` so an idle worker takes queued tests
# from a busy one), a quarter to the container runner's shards (one process per group of test
# files); every process at ONE maths thread, the production setting since decision 353. On the
# Jetstream2 BRAVO's 64 cores that is 48 + 16 processes; on the Mac's 16, 12 + 4.
cd /usr/src/BRAVO || exit 1
NPROC=$(nproc)
HOST_N=$(( NPROC * 3 / 4 )); [ $HOST_N -lt 2 ] && HOST_N=2
CONT_N=$(( NPROC - HOST_N )); [ $CONT_N -lt 2 ] && CONT_N=2
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p _agent_bridge/_suite_logs
LOGS=_agent_bridge/_suite_logs
HOST_TESTS="ClosedLoopDeployment/tests StimOptimizer/tests CacheStore/tests DecodeCommon/tests ControlAnalyses/tests StimRL/tests SurveyForms/tests"
HOST_OPTS="-q -W ignore -p no:cacheprovider"
T0=$(date +%s)

# THE FAST RUN (`--fast`, decision 451): the routine check during work; leaves out the ControlAnalyses
# package and the tests listed in modules/slow_tests.py (marked `slow`). The full run (no argument)
# is the one before every commit.
SLOW_FILTER=""
CONT_FAST=""
if [ "${1:-}" = "--fast" ]; then
  SLOW_FILTER=" and not slow"
  CONT_FAST="--fast"
  HOST_TESTS="ClosedLoopDeployment/tests StimOptimizer/tests CacheStore/tests DecodeCommon/tests StimRL/tests SurveyForms/tests"
fi

if [ "${1:-}" = "--live" ]; then
  ( cd modules && PYTHONPATH=. python3 -B -m pytest $HOST_TESTS $HOST_OPTS -m "live" > ../$LOGS/host_live.log 2>&1 ) &
  HOST=$!
  ( python3 _agent_bridge/run_tests.py --live > $LOGS/container_live.log 2>&1 ) &
  CONT=$!
  wait $HOST; wait $CONT
  echo "host (live only):      $(rg 'passed|failed|error|deselected|no tests ran' $LOGS/host_live.log | rg -v '^R\[' | tail -1)"
  echo "container (live only): $(rg 'PASS=|FAIL=' $LOGS/container_live.log | tail -1)"
  echo "wall: $(( $(date +%s) - T0 )) s"
  exit 0
fi

(
  cd modules || exit 1
  # pass 1: everything routine, across HOST_N processes, one maths thread each
  PYTHONPATH=. python3 -B -m pytest $HOST_TESTS $HOST_OPTS -n $HOST_N --dist worksteal \
    -m "not live and not store$SLOW_FILTER" > ../$LOGS/host_parallel.log 2>&1
  # pass 2: the store tests, one at a time, default threads
  PYTHONPATH=. python3 -B -m pytest $HOST_TESTS $HOST_OPTS -m "store and not live" > ../$LOGS/host_store.log 2>&1
) &
HOST=$!
( python3 _agent_bridge/run_tests.py --shards $CONT_N $CONT_FAST > $LOGS/container.log 2>&1 ) &
CONT=$!
wait $HOST; wait $CONT

P1=$(rg 'passed|failed|error|deselected|no tests ran' $LOGS/host_parallel.log | rg -v '^R\[' | tail -1)
P2=$(rg 'passed|failed|error|deselected|no tests ran' $LOGS/host_store.log | rg -v '^R\[' | tail -1)
# the arithmetic across the two host passes, so one line carries the whole host count
TOTAL=$(cat $LOGS/host_parallel.log $LOGS/host_store.log | python3 -c '
import re, sys
n = {"passed": 0, "skipped": 0, "failed": 0, "error": 0}
for line in sys.stdin:
    if re.search(r"\d+ (passed|failed|skipped|error|deselected)", line) and " in " in line:
        for k in n:
            m = re.search(r"(\d+) " + k, line)
            if m:
                n[k] += int(m.group(1))
print("%d passed, %d skipped, %d failed, %d errors" % (n["passed"], n["skipped"], n["failed"], n["error"]))')
echo "host:      $TOTAL  [parallel: $P1 | store, serial: $P2]"
echo "container: $(rg 'PASS=|FAIL=' $LOGS/container.log | tail -1)"
rg "slowest file" $LOGS/container.log | head -3
echo "wall: $(( $(date +%s) - T0 )) s ${CONT_FAST:+(FAST run: slow tests left out; full run before committing)}  (the live tests are not in this run: sh _agent_bridge/run_both_suites.sh --live)"
