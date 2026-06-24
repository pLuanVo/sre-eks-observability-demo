"""SLO burn rate calculation tool."""

import requests
import config


def register(mcp):
    @mcp.tool()
    def slo_burn_rate(service: str, slo_type: str = "availability") -> str:
        """Calculate SLO burn rate for a service.

        Args:
            service: Service name (e.g. 'payment-service')
            slo_type: SLO type — 'availability' or 'latency'
        """
        slo_target = 0.995

        if slo_type == "availability":
            query = (
                f'sum(rate(http_requests_total{{service="{service}",code=~"5.."}}[5m])) / '
                f'sum(rate(http_requests_total{{service="{service}"}}[5m]))'
            )
        elif slo_type == "latency":
            query = (
                f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket'
                f'{{service="{service}"}}[5m])) by (le))'
            )
            return _query_vm(query, f"p99 latency for {service} (target: <500ms)")
        else:
            return f"Unknown SLO type: {slo_type}"

        try:
            resp = requests.get(
                f"{config.VM_URL}/api/v1/query",
                params={"query": query},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("data", {}).get("result", [])
            if not results:
                return f"No data for {service} availability"

            error_rate = float(results[0]["value"][1])
            error_budget = 1 - slo_target
            burn_rate = error_rate / error_budget if error_budget > 0 else 0
            availability = (1 - error_rate) * 100
            budget_remaining = max(0, (1 - error_rate / error_budget)) * 100

            return (
                f"SLO Burn Rate for {service}:\n"
                f"  Current availability: {availability:.3f}%\n"
                f"  SLO target: {slo_target * 100}%\n"
                f"  Error rate (5m): {error_rate:.6f}\n"
                f"  Burn rate: {burn_rate:.2f}x\n"
                f"  Error budget remaining: {budget_remaining:.1f}%\n"
                f"  Status: {'OK' if burn_rate < 1 else 'WARNING' if burn_rate < 6 else 'CRITICAL'}"
            )
        except Exception as e:
            return f"Error calculating burn rate: {e}"


def _query_vm(query, desc):
    try:
        resp = requests.get(f"{config.VM_URL}/api/v1/query", params={"query": query}, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("data", {}).get("result", [])
        if not results:
            return f"{desc}: no data"
        value = results[0]["value"][1]
        return f"{desc}: {value}"
    except Exception as e:
        return f"Error: {e}"
