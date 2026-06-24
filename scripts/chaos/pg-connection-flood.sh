#!/usr/bin/env bash
set -euo pipefail
COUNT=${1:-80}
echo "Flooding PostgreSQL with ${COUNT} idle connections..."
kubectl exec -n demo deploy/payment-service -- curl -s -X POST http://localhost:8082/chaos/pg-flood \
  -H "Content-Type: application/json" -d "{\"count\": $COUNT}"
echo ""
