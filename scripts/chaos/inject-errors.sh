#!/usr/bin/env bash
set -euo pipefail
RATE=${1:-30}
echo "Injecting ${RATE}% error rate into payment-service..."
kubectl exec -n demo deploy/payment-service -- curl -s -X POST http://localhost:8082/chaos/errors \
  -H "Content-Type: application/json" -d "{\"rate\": $RATE}"
echo ""
