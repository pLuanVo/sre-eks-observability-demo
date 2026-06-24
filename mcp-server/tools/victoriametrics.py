"""VictoriaMetrics query tool — MetricsQL (superset of PromQL)."""

import requests
import config


def register(mcp):
    @mcp.tool()
    def query_metrics(query: str, time_range: str = "5m") -> str:
        """Execute a MetricsQL query against VictoriaMetrics.

        Args:
            query: MetricsQL/PromQL expression
            time_range: Time range for range queries (e.g. '5m', '1h')
        """
        try:
            resp = requests.get(
                f"{config.VM_URL}/api/v1/query",
                params={"query": query},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("data", {}).get("result", [])
            if not results:
                return f"No results for query: {query}"
            lines = []
            for r in results[:20]:
                metric = r.get("metric", {})
                value = r.get("value", [None, "N/A"])
                label_str = ", ".join(f"{k}={v}" for k, v in metric.items())
                lines.append(f"  {label_str}: {value[1]}")
            return f"Query: {query}\nResults ({len(results)}):\n" + "\n".join(lines)
        except Exception as e:
            return f"Error querying VictoriaMetrics: {e}"
