# Case 4: Bad Deployment Auto-Rollback (L1 Auto-Remediation)

## What This Demonstrates

End-to-end detection AND automated rollback of a broken container deployment. When a pod enters CrashLoopBackOff (the most common deployment failure mode in Kubernetes), the MCP server automatically rolls back to the last known-good revision. This scenario validates the L1 auto-remediation path for deployment failures -- a safe, deterministic fix that leverages Kubernetes' built-in rollout history.

## Real-World Scenario

An engineer deploys a new version of payment-service with a broken container image. The pods fail to start, entering an ImagePullBackOff or CrashLoopBackOff loop. Without automated rollback, this causes:
- Service degradation (if `maxUnavailable > 0`, some pods are down)
- Complete outage (if all replicas are replaced simultaneously)
- Alert fatigue (cascading alerts from dependent services)
- Extended MTTR (mean time to recovery) if the on-call SRE is asleep

## Chaos Injection

The `scripts/chaos/deploy-broken.sh` script patches the payment-service deployment with a non-functional image:

```bash
# Via the chaos script
./scripts/chaos/deploy-broken.sh
```

The script executes:
```bash
kubectl set image deployment/payment-service \
  payment-service=busybox:latest -n demo
```

This replaces the payment-service container image with `busybox:latest` -- a minimal Linux image that does not contain a Python runtime or Flask application. The container starts but immediately exits because there is no matching entrypoint, causing Kubernetes to restart it repeatedly (CrashLoopBackOff).

## What Happens (Step by Step)

```
1. kubectl patches payment-service deployment with busybox:latest
   Kubernetes creates new ReplicaSet with the broken image

2. New pods start but immediately crash:
   - Container starts busybox
   - No CMD/ENTRYPOINT matches the Flask app
   - Container exits with non-zero code
   - kubelet restarts container (backoff: 10s, 20s, 40s, 80s...)
   - Pod status: CrashLoopBackOff

3. kube-state-metrics reports pod failures:
   kube_pod_container_status_restarts_total increases
   kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"} = 1

4. VMAlert evaluates PodCrashLooping rule:
   increase(kube_pod_container_status_restarts_total{namespace="demo"}[15m]) > 3
   Alert fires after 5 minutes sustained

5. VMAlertmanager routes alert to MCP server webhook (:8091/webhook)

6. MCP server webhook handler:
   - Receives alert with alertname="PodCrashLooping"
   - Reads sre/runbooks/deployment-failure.md
   - Checks for "AUTO-REMEDIATION: ELIGIBLE" marker
   - Marker FOUND → returns {"level": "L1", "action": "auto-remediate"}

7. MCP server remediation tool executes rollback_deployment:
   kubectl rollout undo deployment/payment-service -n demo

8. Kubernetes rolls back to the previous ReplicaSet:
   - Previous revision's image (the working ECR image) is restored
   - New pods start with the correct image
   - Old crashing pods are terminated

9. Recovery verification:
   - All pods reach Running status
   - Health endpoint (/healthz) returns 200
   - kube_pod_container_status_restarts_total stops increasing
   - Request flow (api-gateway -> order-service -> payment-service) resumes
   - Alert resolves → success logged
```

## Expected Observations

### During CrashLoopBackOff

```bash
$ kubectl get pods -n demo -l app.kubernetes.io/name=payment-service
NAME                               READY   STATUS             RESTARTS   AGE
payment-service-abc123-xxxxx       0/1     CrashLoopBackOff   4          3m
payment-service-abc123-yyyyy       0/1     CrashLoopBackOff   4          3m
```

### VMSingle vmui Queries

Pod restart count:
```metricsql
increase(kube_pod_container_status_restarts_total{namespace="demo", container="payment-service"}[15m])
```
Expected result: > 3 (triggering the alert threshold).

Pods in waiting state:
```metricsql
kube_pod_container_status_waiting_reason{namespace="demo", reason="CrashLoopBackOff"}
```
Expected result: > 0 for payment-service pods.

### After Rollback

```bash
$ kubectl get pods -n demo -l app.kubernetes.io/name=payment-service
NAME                               READY   STATUS    RESTARTS   AGE
payment-service-def456-xxxxx       1/1     Running   0          45s
payment-service-def456-yyyyy       1/1     Running   0          42s

$ kubectl rollout history deployment/payment-service -n demo
REVISION  CHANGE-CAUSE
1         <initial deployment>
2         <broken busybox image>
3         <rollback to revision 1>
```

## Why L1 (Auto-Remediation Safe)

The `sre/runbooks/deployment-failure.md` runbook is marked `AUTO-REMEDIATION: ELIGIBLE`. The rollback action meets all safety criteria:

| Criterion | Assessment |
|-----------|------------|
| **Deterministic** | `kubectl rollout undo` restores the exact previous ReplicaSet -- same image, same config, same resource limits. The outcome is predictable. |
| **Reversible** | If the rollback was wrong (unlikely), the team can re-deploy the intended version manually. No data is lost. |
| **Low risk** | The previous version was already running successfully in production. Rolling back to it is the lowest-risk action available. |
| **Standard practice** | Kubernetes rollback is a first-class operation. `Deployment.spec.revisionHistoryLimit` (default 10) maintains rollback targets. |

### MCP Remediation Implementation

The MCP server's `execute_remediation` tool (in `mcp-server/tools/remediation.py`) implements the `rollback_deployment` action:

```python
def _run_kubectl(args):
    result = subprocess.run(
        f"kubectl {args}".split(),
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        return f"Success: kubectl {args}\n{result.stdout}"
    return f"Error: kubectl {args}\n{result.stderr}"

# Called as:
_run_kubectl(f"rollout undo deployment/{target} -n {ns}")
```

## Alert Rule Details

From `observability/rules/alerts.yaml`:

```yaml
- alert: PodCrashLooping
  expr: |
    increase(kube_pod_container_status_restarts_total{namespace="demo"}[15m]) > 3
  for: 5m
  labels:
    severity: critical
    team: sre
  annotations:
    summary: "Pod {{ $labels.namespace }}/{{ $labels.pod }} is crash-looping"
    description: >-
      Container {{ $labels.container }} in pod {{ $labels.pod }}
      has restarted {{ $value }} times in the last 15 minutes.
```

The combination of `increase(...[15m]) > 3` with `for: 5m` ensures:
- At least 3 restarts in 15 minutes (confirms sustained failure, not a one-off OOM kill)
- Condition persists for 5 minutes (avoids firing during normal rolling updates where old pods terminate)

## Recovery Verification

After rollback, the MCP server (and the human SRE reviewing the incident) verify recovery via:

1. **Pod status**: All pods in `Running` state, no `CrashLoopBackOff`
2. **Health endpoint**: `curl payment-service:8082/healthz` returns `{"status": "healthy"}`
3. **Metrics resumption**: `http_requests_total` for payment-service resumes incrementing
4. **Error rate**: `sli:error_rate:rate5m` returns to 0 (baseline)
5. **Dependent services**: api-gateway and order-service request flows succeed end-to-end

## Production Application

Automated rollback for CrashLoopBackOff is widely adopted in production Kubernetes environments:

### Progressive Delivery Tools

| Tool | Approach |
|------|----------|
| **Argo Rollouts** | Canary/blue-green deployments with automated rollback on metric degradation |
| **Flagger** | Progressive delivery with automated analysis and rollback |
| **Kubernetes native** | `kubectl rollout undo` (what this demo uses) |

### Deployment Best Practices

| Practice | Purpose |
|----------|---------|
| `maxUnavailable: 0`, `maxSurge: 1` | Zero-downtime rolling updates -- new pod must be healthy before old pod terminates |
| **Readiness probes** with `initialDelaySeconds` | Prevents traffic routing to pods that haven't finished startup |
| **Liveness probes** with `failureThreshold` | Detects stuck processes (deadlocks, infinite loops) |
| **PodDisruptionBudget** | Prevents too many pods dying simultaneously during voluntary disruptions |
| **revisionHistoryLimit: 10** | Maintains rollback targets for the last 10 deployments |

### Post-Rollback Process

Automated rollback restores service availability, but the root cause must still be investigated:
1. **Mandatory post-mortem**: Why did the broken image reach production?
2. **CI/CD gap analysis**: Were integration tests skipped? Was the image validated?
3. **Deployment notification**: Inform the deploying team that their release was automatically rolled back
4. **Re-deploy with fix**: After root cause is addressed, deploy again through the standard pipeline
