#!/usr/bin/env bash
set -euo pipefail

echo "=== Port forwarding observability services ==="

kubectl port-forward svc/vmsingle-victoria-metrics 8429:8429 -n observability &
echo "  VictoriaMetrics: http://localhost:8429"

kubectl port-forward svc/grafana 3000:3000 -n observability &
echo "  Grafana:         http://localhost:3000"

kubectl port-forward svc/api-gateway 8080:8080 -n demo &
echo "  API Gateway:     http://localhost:8080"

kubectl port-forward svc/mcp-server 8090:8090 -n demo &
echo "  MCP Server:      http://localhost:8090"

echo ""
echo "Press Ctrl+C to stop all port-forwards."
wait
