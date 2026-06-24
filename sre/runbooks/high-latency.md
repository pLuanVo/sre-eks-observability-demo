# Runbook: High Latency

## Symptom
p99 latency exceeds 500ms SLO target. Visible in Grafana SLO overview dashboard.

## AUTO-REMEDIATION: NOT ELIGIBLE (requires investigation)

## Triage Steps

### Step 1: Identify affected service (~1 min)
```metricsql
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))
```

### Step 2: Check if latency correlates with deployment (~1 min)
```bash
kubectl rollout history deployment/<service> -n demo
```

### Step 3: Check downstream dependencies (~2 min)
```metricsql
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{service="payment-service"}[5m])) by (le))
```

### Step 4: Check PostgreSQL query latency (~2 min)
```sql
SELECT query, calls, round(mean_exec_time::numeric, 2) as mean_ms
FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;
```

### Step 5: Check resource utilization (~1 min)
```bash
kubectl top pods -n demo
```

## Mitigation

| Scenario | Action |
|----------|--------|
| Downstream slow | Investigate downstream service |
| PG slow queries | See pg-slow-queries runbook |
| CPU/memory pressure | Scale horizontally or increase limits |
| Network congestion | Check node-level metrics |

## Escalation
- Notify team channel if p99 > 1s for > 5 minutes
