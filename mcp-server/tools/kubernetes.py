"""Kubernetes status tool — pods, deployments, events."""

from kubernetes import client, config as k8s_config
import config


def register(mcp):
    @mcp.tool()
    def k8s_status(resource: str = "pods", namespace: str = "") -> str:
        """Get Kubernetes resource status.

        Args:
            resource: Resource type ('pods', 'deployments', 'events')
            namespace: Namespace (default: demo)
        """
        ns = namespace or config.K8S_NAMESPACE
        try:
            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                k8s_config.load_kube_config()

            if resource == "pods":
                return _get_pods(ns)
            elif resource == "deployments":
                return _get_deployments(ns)
            elif resource == "events":
                return _get_events(ns)
            else:
                return f"Unknown resource type: {resource}. Use 'pods', 'deployments', or 'events'."
        except Exception as e:
            return f"Error: {e}"


def _get_pods(ns):
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace=ns)
    lines = []
    for p in pods.items:
        restarts = sum(cs.restart_count for cs in (p.status.container_statuses or []))
        lines.append(f"  {p.metadata.name}: {p.status.phase} (restarts={restarts})")
    return f"Pods in {ns} ({len(lines)}):\n" + "\n".join(lines)


def _get_deployments(ns):
    apps = client.AppsV1Api()
    deps = apps.list_namespaced_deployment(namespace=ns)
    lines = []
    for d in deps.items:
        ready = d.status.ready_replicas or 0
        desired = d.spec.replicas or 0
        lines.append(f"  {d.metadata.name}: {ready}/{desired} ready")
    return f"Deployments in {ns} ({len(lines)}):\n" + "\n".join(lines)


def _get_events(ns):
    v1 = client.CoreV1Api()
    events = v1.list_namespaced_event(namespace=ns)
    recent = sorted(events.items, key=lambda e: e.last_timestamp or e.event_time or "", reverse=True)[:15]
    lines = []
    for e in recent:
        lines.append(f"  [{e.type}] {e.involved_object.name}: {e.reason} — {e.message}")
    return f"Recent events in {ns} ({len(lines)}):\n" + "\n".join(lines)
