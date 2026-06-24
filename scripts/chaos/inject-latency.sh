#!/usr/bin/env bash
set -euo pipefail
DELAY_MS=${1:-2000}
echo "Injecting ${DELAY_MS}ms latency into payment-service..."
kubectl exec -n demo deploy/payment-service -- curl -s -X POST http://localhost:8082/chaos/latency \
  -H "Content-Type: application/json" -d "{\"delay_ms\": $DELAY_MS}"
echo ""
