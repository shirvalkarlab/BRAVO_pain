#!/bin/sh
# Both test suites at once, in one bridge job, on the container's 16 cores. Each writes its own
# log; the summary lines are printed together at the end. Sequentially they cost about 116 s
# (host, pytest) + 78 s (container, run_tests.py); side by side the wall clock is the longer one.
# Usage (from the repository root on the host):
#   python3 BRAVO/_agent_bridge/bridge_client.py --cwd /usr/src/BRAVO --timeout 900 --wait 5 "sh _agent_bridge/run_both_suites.sh"
# then poll BRAVO/_agent_bridge/outbox/<job>.out.
cd /usr/src/BRAVO || exit 1
mkdir -p _agent_bridge/_suite_logs
( cd modules && PYTHONPATH=. python3 -B -m pytest ClosedLoopDeployment/tests StimOptimizer/tests CacheStore/tests DecodeCommon/tests -q -W ignore > ../_agent_bridge/_suite_logs/host.log 2>&1 ) &
HOST=$!
( python3 _agent_bridge/run_tests.py > _agent_bridge/_suite_logs/container.log 2>&1 ) &
CONT=$!
wait $HOST; wait $CONT
echo "host:      $(grep -E 'passed|failed|error' _agent_bridge/_suite_logs/host.log | grep -v '^R\[' | tail -1)"
echo "container: $(grep -E 'PASS=|FAIL=' _agent_bridge/_suite_logs/container.log | tail -1)"
