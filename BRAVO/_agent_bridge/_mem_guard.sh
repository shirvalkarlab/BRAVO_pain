#!/bin/sh
# Sample memory every 3 s into $1; stop the measurement if less than 8 GB is left.
sleep 5
while docker exec bravo_pain-bravo-server-1 pgrep -f _measure_rating_pass.py >/dev/null 2>&1; do
  avail=$(free -m | awk '/Mem:/{print $7}')
  echo "$(date -u +%T) used=$(free -m | awk '/Mem:/{print $3}') avail=$avail" >> "$1"
  if [ "$avail" -lt 8000 ]; then
    echo "$(date -u +%T) GUARD: under 8 GB left, stopping" >> "$1"
    docker exec bravo_pain-bravo-server-1 sh -c 'pkill -TERM -f "_measure_rating_pass.py"; sleep 2; pkill -KILL -f "multiprocessing.spawn"'
    break
  fi
  sleep 3
done
