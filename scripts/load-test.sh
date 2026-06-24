#!/usr/bin/env bash
set -euo pipefail

DURATION=${1:-300}
RPS=${2:-5}
TARGET=${3:-"http://localhost:8080/order"}

echo "=== Load test: $RPS RPS for ${DURATION}s → $TARGET ==="

INTERVAL=$(echo "scale=3; 1/$RPS" | bc)
END=$((SECONDS + DURATION))

while [ $SECONDS -lt $END ]; do
  curl -s -o /dev/null -w "%{http_code}" "$TARGET" &
  sleep "$INTERVAL"
done

wait
echo "Load test complete."
