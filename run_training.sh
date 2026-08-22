#!/bin/bash
# Unattended training. Restarts from models/latest.zip after a crash, until
# the cumulative step target is reached.
#   ./run_training.sh [steps] [max_restarts]
cd "$(dirname "$0")"
STEPS="${1:-50000}"
MAX_RESTARTS="${2:-40}"
STAMP=$(date +%Y%m%d_%H%M%S)
LOG="logs/train_${STAMP}.log"
mkdir -p logs models

{
  for i in $(seq 0 "$MAX_RESTARTS"); do
    echo "=== attempt $i @ $(date '+%H:%M:%S') ==="
    PYTHONPATH=. ./venv/bin/python -u -m src.train \
      --steps "$STEPS" --eval-every 2000 --eval-episodes 4
    code=$?
    if [ $code -eq 0 ]; then echo "=== finished cleanly ==="; break; fi
    echo "=== exited $code, restarting from latest checkpoint in 15s ==="
    pkill -9 -f "MacOS/Dolphin" 2>/dev/null
    sleep 15
  done
} > "$LOG" 2>&1 &

echo "pid $!  ->  $LOG"
echo "watch:   tail -f $LOG"
