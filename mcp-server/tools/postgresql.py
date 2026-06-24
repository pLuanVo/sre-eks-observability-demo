"""PostgreSQL diagnostics tool — connections, slow queries, locks, table stats."""

import psycopg2
import config


def register(mcp):
    @mcp.tool()
    def pg_diagnostics(check: str) -> str:
        """Run PostgreSQL diagnostic queries.

        Args:
            check: Type of check — 'connections', 'slow_queries', 'locks', 'table_stats'
        """
        queries = {
            "connections": (
                "SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY count DESC",
                "Connection count by state",
            ),
            "slow_queries": (
                "SELECT left(query, 80) as query, calls, round(mean_exec_time::numeric, 2) as mean_ms, "
                "round(total_exec_time::numeric, 2) as total_ms "
                "FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10",
                "Top 10 slowest queries (by mean exec time)",
            ),
            "locks": (
                "SELECT pid, locktype, mode, granted, left(query, 60) as query "
                "FROM pg_locks l JOIN pg_stat_activity a ON l.pid = a.pid "
                "WHERE NOT granted ORDER BY pid",
                "Waiting (blocked) locks",
            ),
            "table_stats": (
                "SELECT relname, seq_scan, idx_scan, n_live_tup, n_dead_tup, "
                "round(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 1) as dead_pct "
                "FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 10",
                "Table scan/dead tuple stats",
            ),
        }

        if check not in queries:
            return f"Unknown check: {check}. Available: {', '.join(queries.keys())}"

        sql, desc = queries[check]
        try:
            conn = psycopg2.connect(config.pg_dsn())
            with conn.cursor() as cur:
                cur.execute(sql)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
            conn.close()

            if not rows:
                return f"{desc}: no results"

            lines = [" | ".join(cols)]
            lines.append("-" * len(lines[0]))
            for row in rows:
                lines.append(" | ".join(str(v) for v in row))
            return f"{desc}:\n" + "\n".join(lines)
        except Exception as e:
            return f"Error running {check}: {e}"
