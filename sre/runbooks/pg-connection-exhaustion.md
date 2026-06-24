# Runbook: PostgreSQL Connection Exhaustion

## Symptom
Alert `PostgreSQLConnectionsNearLimit` fires. Connection utilization > 80% of max_connections.

## AUTO-REMEDIATION: ELIGIBLE
Action: Terminate idle-in-transaction connections older than 5 minutes.

## Triage Steps

### Step 1: Check current connections (~1 min)
```sql
SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY count DESC;
```

### Step 2: Identify idle-in-transaction (~1 min)
```sql
SELECT pid, usename, state, query_start, left(query, 80) as query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY query_start;
```

### Step 3: Auto-terminate idle connections (~1 min)
```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND query_start < now() - interval '5 minutes'
  AND pid != pg_backend_pid();
```

### Step 4: Verify recovery (~1 min)
```sql
SELECT count(*) FROM pg_stat_activity;
```

## Root Cause Investigation
- Application not releasing connections properly (missing connection pool close)
- Connection pool misconfigured (too many connections per pod)
- Long-running transactions holding connections open

## Prevention
- Implement connection pooling (PgBouncer) for production
- Set `idle_in_transaction_session_timeout` parameter
- Monitor with postgres_exporter + VictoriaMetrics
