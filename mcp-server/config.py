import os

VM_URL = os.environ.get("VM_URL", "http://vmsingle-victoria-metrics.observability:8429")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://grafana.observability:3000")

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_USER = os.environ.get("PG_USER", "sreadmin")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")
PG_DATABASE = os.environ.get("PG_DATABASE", "sre_demo")

K8S_NAMESPACE = os.environ.get("K8S_NAMESPACE", "demo")
RUNBOOK_DIR = os.environ.get("RUNBOOK_DIR", "sre/runbooks")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://localhost:9095/webhook")

MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8090"))
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8091"))


def pg_dsn():
    return f"host={PG_HOST} port={PG_PORT} dbname={PG_DATABASE} user={PG_USER} password={PG_PASSWORD}"
