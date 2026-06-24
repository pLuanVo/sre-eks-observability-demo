# Case 1: Latency Advisory (L2 Escalation)

## What This Demonstrates

End-to-end detection and escalation of elevated API response times caused by a slow downstream dependency. This scenario exercises the full observability pipeline from chaos injection through SLO burn rate alerting to MCP-driven L2 escalation. The key SRE decision here: latency issues require human judgment, so auto-remediation is intentionally NOT triggered.

## Real-World Scenario

A downstream service (payment-service) experiences degraded response times -- this could represent network congestion, a slow database query, an overwhelmed third-party API, or resource contention on shared infrastructure. The upstream services (order-service, api-gateway) inherit the latency, causing SLO violations visible to end users.

## Chaos Injection

The payment-service exposes a `/chaos/latency` endpoint that adds artificial delay to every request:

```bash
# Via the chaos script (recommended -- runs inside the cluster)
./scripts/chaos/inject-latency.sh 2000

# Or directly via kubectl exec
kubectl exec -n demo deploy/payment-service -- \
  curl -s -X POST http://localhost:8082/chaos/latency \
  -H "Content-Type: application/json" \
  -d '{"delay_ms": 2000}'
```

This injects 2000ms of `time.sleep()` into every `/pay` request handler, simulating a slow downstream dependency.

## What Happens (Step by Step)

```
1. payment-service /pay responses slow from ~50ms to ~2050ms
   (chaos_config["latency_ms"] = 2000, applied via time.sleep)

2. order-service calls to payment-service inherit the delay
   (order-service -> payment-service:8082/pay is synchronous)

3. api-gateway /order endpoint p99 latency spikes above 500ms SLO target

4. Recording rules calculate burn rate:
   sli:latency:rate5m jumps to >2s (far above 500ms target)
   sli:error_budget_burn:rate5m rises as latency degrades user experience

5. VMAlert evaluates SLOBurnRateCritical rule:
   sli:error_budget_burn:rate5m > 14.4 AND sli:error_budget_burn:rate1h > 14.4
   Alert fires after 2 minutes sustained

6. VMAlertmanager routes the alert to MCP server webhook (:8091/webhook)

7. MCP server webhook handler:
   - Receives alert payload with alertname + runbook_url
   - Reads sre/runbooks/high-latency.md
   - Checks for "AUTO-REMEDIATION: ELIGIBLE" marker
   - Marker NOT found -> returns {"level": "L2", "action": "escalated"}

8. Alert + runbook link escalated to notification channel for human SRE
```

## Expected Observations

### VMSingle vmui Queries

Average request duration spikes:
```metricsql
rate(http_request_duration_seconds_sum{service="payment-service"}[5m])
/
rate(http_request_duration_seconds_count{service="payment-service"}[5m])
```
Expected result: jumps from ~0.05s to ~2.05s.

p99 latency breaches SLO:
```metricsql
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service)
)
```
Expected result: payment-service p99 > 2s, api-gateway p99 > 2s.

SLO burn rate:
```metricsql
sli:error_budget_burn:rate5m
```
Expected result: exceeds 14.4x threshold.

### VMAlert

- `SLOBurnRateCritical` alert transitions from `inactive` to `pending` to `firing`
- Alert annotations include service name and burn rate value

### MCP Server Logs

```
Alert received: SLOBurnRateCritical, runbook: .../high-latency
L2: Escalating SLOBurnRateCritical to webhook
```

## Why L2 (Not L1 Auto-Remediation)

The `sre/runbooks/high-latency.md` runbook is explicitly marked `AUTO-REMEDIATION: NOT ELIGIBLE (requires investigation)`. This is by design:

| Possible Root Cause | Why Auto-Fix Would Be Wrong |
|---------------------|-----------------------------|
| Network congestion | Transient; may resolve itself. Restart won't help. |
| Downstream API degradation | Not our service to fix. Need to contact the provider. |
| Database query regression | Requires query plan analysis, possibly index creation. |
| Resource contention (CPU/memory) | Needs capacity planning, not a restart. |
| Recent deployment introduced slow code | Rollback might help, but need to confirm correlation first. |

The runbook guides the human SRE through systematic triage:
1. Identify which service is slow (MetricsQL query)
2. Check deployment correlation (`kubectl rollout history`)
3. Inspect downstream dependency latency
4. Check PostgreSQL query latency (`pg_stat_statements`)
5. Check resource utilization (`kubectl top pods`)

## Reset

```bash
# Via chaos script
./scripts/chaos/inject-latency.sh 0

# Or directly
kubectl exec -n demo deploy/payment-service -- \
  curl -s -X POST http://localhost:8082/chaos/latency \
  -H "Content-Type: application/json" \
  -d '{"delay_ms": 0}'

# Or reset all chaos at once
kubectl exec -n demo deploy/payment-service -- \
  curl -s -X DELETE http://localhost:8082/chaos
```

## Production Application

In a production environment, this same pattern integrates with:

- **PagerDuty/Opsgenie**: VMAlertmanager routes critical alerts to on-call pages
- **Slack/Teams**: Warning-level alerts go to team channels with runbook links
- **Multi-window burn rate alerting** (from the Google SRE Workbook): prevents alert fatigue by requiring sustained degradation across multiple time windows
  - **Critical**: 14.4x burn rate over both 5m AND 1h windows (budget exhausted in ~2 days)
  - **Warning**: 6x burn rate over both 30m AND 6h windows (budget exhausted in ~5 days)
- **Deployment correlation**: Production tooling auto-correlates latency spikes with recent deployments to accelerate triage
- **Circuit breakers**: In microservice architectures, downstream latency propagation is mitigated by circuit breaker patterns (not implemented in this demo for simplicity)
