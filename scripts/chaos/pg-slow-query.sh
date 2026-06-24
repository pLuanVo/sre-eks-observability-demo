#!/usr/bin/env bash
set -euo pipefail
DURATION=${1:-30}
echo "Injecting slow queries for ${DURATION}s..."
kubectl exec -n demo deploy/payment-service -- curl -s -X POST http://localhost:8082/chaos/pg-slow \
  -H "Content-Type: application/json" -d "{\"duration_sec\": $DURATION}"
echo ""
