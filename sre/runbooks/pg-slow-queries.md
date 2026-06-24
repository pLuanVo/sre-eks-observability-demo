# Runbook: PostgreSQL Slow Queries

## Symptom
Alert `PostgreSQLSlowQueries` fires. Mean query execution time > 1 second.

## AUTO-REMEDIATION: NOT ELIGIBLE (requires analysis)

## Triage Steps

### Step 1: Identify slow queries (~2 min)
```sql
SELECT query, calls, round(mean_exec_time::numeric, 2) as mean_ms,
       round(total_exec_time::numeric, 2) as total_ms,
       rows
FROM pg_stat_statements
ORDER BY mean_exec_time DESC LIMIT 10;
```

### Step 2: Analyze query plan (~3 min)
```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) <slow_query>;
```

Look for:
- Sequential scans on large tables (missing index)
- Nested loops with high row counts
- High buffer reads (cache misses)

### Step 3: Check table statistics (~1 min)
```sql
SELECT relname, seq_scan, idx_scan, n_live_tup, n_dead_tup
FROM pg_stat_user_tables
ORDER BY seq_scan DESC;
```

### Step 4: Check for lock contention (~1 min)
```sql
SELECT pid, locktype, mode, granted, left(query, 60) as query
FROM pg_locks l JOIN pg_stat_activity a ON l.pid = a.pid
WHERE NOT granted;
```

## Mitigation

| Finding | Action |
|---------|--------|
| Missing index | `CREATE INDEX CONCURRENTLY` on frequently scanned columns |
| Table bloat (high dead tuples) | `VACUUM ANALYZE <table>` |
| Lock contention | Investigate conflicting transactions |
| Inefficient query | Rewrite query, add appropriate WHERE clauses |

## Key Tuning Parameters
- `work_mem`: Increase for complex sorts/joins (default 4MB → 64MB)
- `effective_cache_size`: Set to ~75% total RAM for better planner estimates
- `random_page_cost`: Reduce to 1.1-1.5 for SSD storage (default 4.0)
