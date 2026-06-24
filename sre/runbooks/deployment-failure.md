# Runbook: Deployment Failure (CrashLoopBackOff)

## Symptom
Alert `PodCrashLooping` fires. Pods in CrashLoopBackOff state with increasing restart count.

## AUTO-REMEDIATION: ELIGIBLE
Action: `kubectl rollout undo deployment/<service> -n demo`

## Triage Steps

### Step 1: Identify crashing pods (~1 min)
```bash
kubectl get pods -n demo | grep -E "CrashLoop|Error"
```

### Step 2: Check pod events (~1 min)
```bash
kubectl describe pod <pod-name> -n demo | tail -20
```

### Step 3: Check container logs (~1 min)
```bash
kubectl logs <pod-name> -n demo --previous
```

### Step 4: Check recent rollout (~1 min)
```bash
kubectl rollout history deployment/<service> -n demo
```

### Step 5: Auto-rollback (~1 min)
```bash
kubectl rollout undo deployment/<service> -n demo
kubectl rollout status deployment/<service> -n demo --timeout=120s
```

## Post-Recovery
- Verify service health in Grafana
- Check error rate returned to baseline
- Create post-mortem if error budget was consumed
