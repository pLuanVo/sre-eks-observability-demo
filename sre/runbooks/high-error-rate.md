# Runbook: High Error Rate

## Symptom
Alert `SLOBurnRateCritical` or `SLOBurnRateWarning` fires. Error rate exceeds SLO budget burn threshold.

## AUTO-REMEDIATION: NOT ELIGIBLE (requires human judgment)

## Severity Assessment

| Burn Rate | Severity | Action |
|-----------|----------|--------|
| > 14.4x (5m AND 1h) | P1 Critical | Immediate response |
| > 6x (30m AND 6h) | P2 Warning | Investigate within 30 min |
| < 6x | Informational | Monitor |

## Triage Steps

### Step 1: Identify affected service (~1 min)
```metricsql
sum(rate(http_requests_total{code=~"5.."}[5m])) by (service)
```

### Step 2: Check error breakdown (~2 min)
```metricsql
sum(rate(http_requests_total{code=~"5.."}[5m])) by (service, endpoint, code)
```

### Step 3: Check recent deployments (~1 min)
```bash
kubectl rollout history deployment/<service> -n demo
```

### Step 4: Check pod health (~1 min)
```bash
kubectl get pods -n demo -l app=<service>
kubectl describe pod <pod-name> -n demo
```

### Step 5: Check logs for errors (~2 min)
```bash
kubectl logs -n demo -l app=<service> --tail=50 | grep -i error
```

## Mitigation

| Scenario | Action |
|----------|--------|
| Recent deployment caused errors | `kubectl rollout undo deployment/<service> -n demo` |
| Downstream service unavailable | Check dependency health, consider circuit breaker |
| Database connection errors | Check PG connections (see pg-connection-exhaustion runbook) |
| Resource exhaustion | Scale pods or increase resource limits |

## Escalation
- P1: Page on-call SRE immediately
- P2: Notify team channel, investigate within 30 min
