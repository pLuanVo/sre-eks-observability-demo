# Post-Mortem: Payment Service P99 Latency Spike

## Metadata

| Field | Value |
|-------|-------|
| Date | 2026-06-20 |
| Duration | 25 minutes |
| Severity | P2 |
| Author | Luan Vo |
| Reviewers | SRE Team |

## Summary

On 2026-06-20, the payment-service experienced a P99 latency spike exceeding the 500ms SLO target for 25 minutes during a scheduled load test. The root cause was a sequential scan on the `payments` table due to a missing index on the `created_at` column. As order volume increased during the load test, PostgreSQL fell back to a full table scan for time-range queries used by the `/payments/recent` endpoint. The issue was resolved by adding a B-tree index on `payments.created_at`, after which P99 latency returned to ~120ms. Total error budget consumed: 3.2% of the 30-day latency SLO window.

## Impact

- **Users affected:** All clients calling the payment-service `/payments/recent` and `/payments/summary` endpoints
- **Services affected:** payment-service (direct), api-gateway (upstream timeout retries increased load)
- **Error budget consumed:** 3.2% of 30-day latency SLO (0.5% budget)
- **SLA impact:** No external SLA breach; internal SLO violated for 25 minutes

## Timeline (UTC+7)

| Time | Event |
|------|-------|
| 14:00 | Scheduled load test started via `scripts/load-test.sh` — 200 concurrent users |
| 14:08 | VMAlert fires `SLOLatencyBurnRateCritical` — 14.4x burn rate on 5-minute window for payment-service |
| 14:09 | Alert delivered to #sre-alerts via VMAlertmanager webhook |
| 14:11 | On-call SRE acknowledges alert, opens Grafana SLO dashboard |
| 14:14 | Grafana confirms payment-service P99 at 1,200ms (SLO target: 500ms). api-gateway and order-service unaffected |
| 14:17 | SRE checks postgres-exporter metrics: `pg_stat_user_tables_seq_scan` on `payments` table spiking from ~2/min to ~350/min |
| 14:20 | `EXPLAIN ANALYZE` on the slow query confirms sequential scan: `Seq Scan on payments (cost=0.00..18432.00 rows=52000 width=128) Filter: (created_at > now() - interval '1 hour')` |
| 14:22 | Root cause confirmed: no index on `payments.created_at`. Fix prepared: `CREATE INDEX CONCURRENTLY idx_payments_created_at ON payments (created_at)` |
| 14:25 | Index creation completed (table size ~500K rows in load test). Verified via `EXPLAIN ANALYZE` — now using Index Scan (cost reduced 98%) |
| 14:28 | P99 latency drops to 130ms. VMAlert resolves `SLOLatencyBurnRateCritical` |
| 14:33 | Load test continues for 30 more minutes with no further SLO violations. Incident closed |

## Root Cause

The `payment-service` queries recent payments using a `WHERE created_at > NOW() - INTERVAL '1 hour'` clause. Under normal traffic (~10 req/s), PostgreSQL's query planner chose a sequential scan which completed within acceptable latency because the table was small (~5K rows in staging).

During the load test, two factors combined to cause the latency spike:

1. **Increased table size**: The load test generator created ~500K payment records, making the sequential scan significantly more expensive.
2. **Increased query concurrency**: 200 concurrent users each hitting `/payments/recent` caused ~350 sequential scans per minute, saturating disk I/O on the RDS instance.

The `payments` table was created in `db-init-job.yaml` without an index on `created_at`. This was an oversight during initial schema design — the `orders` table already had a similar index.

## Detection

Detection was fast and automated:

- **VMAlert** fired `SLOLatencyBurnRateCritical` within 8 minutes of the load test starting, using the multi-window burn rate alerting rule (14.4x burn rate on 5-minute window, confirmed by 6x on 1-hour window).
- **VMAlertmanager** delivered the alert to #sre-alerts within 1 minute.
- **Grafana SLO dashboard** immediately showed the latency spike isolated to payment-service.

Detection quality was good. The multi-window burn rate approach avoided false positives while catching the issue before significant budget was consumed.

## Resolution

1. Connected to the RDS instance via `kubectl exec` into a debug pod with `psql`.
2. Ran `CREATE INDEX CONCURRENTLY idx_payments_created_at ON payments (created_at)` — used `CONCURRENTLY` to avoid locking the table during the active load test.
3. Verified the new index was being used via `EXPLAIN ANALYZE`.
4. Confirmed P99 latency returned to normal (~130ms) on the Grafana dashboard.
5. Allowed the load test to continue for 30 additional minutes to validate stability.

## What Went Well

- Multi-window burn rate alerting detected the issue quickly (8 minutes) and did not produce false positives
- postgres-exporter metrics (`pg_stat_user_tables_seq_scan`) immediately pointed to the problematic table, reducing investigation time
- `CREATE INDEX CONCURRENTLY` allowed the fix to be applied without stopping the load test or causing additional downtime
- Grafana SLO dashboard provided clear visualization of per-service latency, isolating payment-service quickly

## What Went Wrong

- The `payments` table was missing an index that the `orders` table already had — inconsistent schema setup in `db-init-job.yaml`
- No pre-deploy checklist item to verify query plans against expected load patterns
- The `pg_slow_queries` runbook exists but was not consulted during initial schema review
- Load test was started without first validating query performance on the populated dataset

## Action Items

| Action | Owner | Priority | Deadline |
|--------|-------|----------|----------|
| Add `CREATE INDEX idx_payments_created_at ON payments (created_at)` to `db-init-job.yaml` | Luan Vo | P1 | 2026-06-21 |
| Add `pg_slow_queries` runbook check to pre-deploy checklist | Luan Vo | P2 | 2026-06-22 |
| Audit all tables for missing indexes on columns used in WHERE/ORDER BY clauses | Luan Vo | P2 | 2026-06-25 |
| Add a load-test warm-up step that validates P99 at 10% traffic before ramping to full load | Luan Vo | P3 | 2026-06-30 |
| Add `pg_stat_user_tables_seq_scan` threshold alert (> 100/min on any table) to VMAlert rules | Luan Vo | P3 | 2026-06-30 |

## Lessons Learned

1. **Index parity across tables**: When multiple tables share similar query patterns (time-range queries), ensure indexes are consistent. A checklist or schema linter could catch this automatically.

2. **Load testing exposes schema gaps**: Small tables mask missing indexes because sequential scans are fast on few rows. Always load-test with realistic data volumes before production deployment.

3. **Observability pays off**: The combination of VictoriaMetrics SLO burn rate alerts + postgres-exporter table-level metrics reduced mean time to root cause (MTTRC) to under 10 minutes. Without postgres-exporter, we would have needed to SSH into the database to diagnose.

4. **`CREATE INDEX CONCURRENTLY` is essential for production**: The ability to add indexes without locking the table meant zero additional downtime during remediation. This should be the default approach for all index additions.
