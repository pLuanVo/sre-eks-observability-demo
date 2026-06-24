"""Log query tool — reads pod logs via Kubernetes API."""

from kubernetes import client, config as k8s_config
import config


def register(mcp):
    @mcp.tool()
    def query_logs(service: str, level: str = "", since: str = "15m", tail: int = 50) -> str:
        """Query recent logs from a service's pods.

        Args:
            service: Service name (e.g. 'payment-service')
            level: Filter by log level ('ERROR', 'WARNING', etc.)
            since: Time window (e.g. '15m', '1h')
            tail: Number of recent lines to return
        """
        try:
            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                k8s_config.load_kube_config()

            v1 = client.CoreV1Api()
            pods = v1.list_namespaced_pod(
                namespace=config.K8S_NAMESPACE,
                label_selector=f"app={service}",
            )

            all_logs = []
            for pod in pods.items[:3]:
                try:
                    since_seconds = _parse_duration(since)
                    logs = v1.read_namespaced_pod_log(
                        name=pod.metadata.name,
                        namespace=config.K8S_NAMESPACE,
                        tail_lines=tail,
                        since_seconds=since_seconds,
                    )
                    for line in logs.strip().split("\n"):
                        if level and level.upper() not in line.upper():
                            continue
                        all_logs.append(f"[{pod.metadata.name}] {line}")
                except Exception:
                    pass

            if not all_logs:
                return f"No logs found for {service} (level={level}, since={since})"
            return f"Logs for {service} ({len(all_logs)} lines):\n" + "\n".join(all_logs[-tail:])
        except Exception as e:
            return f"Error reading logs: {e}"


def _parse_duration(s: str) -> int:
    s = s.strip()
    if s.endswith("m"):
        return int(s[:-1]) * 60
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    if s.endswith("s"):
        return int(s[:-1])
    return 900
