"""SRE Observability MCP Server — VictoriaMetrics, Vector, K8s, PostgreSQL, SLO, Runbooks, Remediation."""

import logging
import threading

from mcp.server.fastmcp import FastMCP

import config
import webhook
from tools.victoriametrics import register as reg_vm
from tools.vector_logs import register as reg_logs
from tools.kubernetes import register as reg_k8s
from tools.postgresql import register as reg_pg
from tools.slo import register as reg_slo
from tools.runbook import register as reg_runbook
from tools.remediation import register as reg_remediation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sre-mcp")

mcp = FastMCP(
    "sre-observability",
    host=config.MCP_HOST,
    port=config.MCP_PORT,
    instructions=(
        "SRE Observability MCP Server for AWS EKS platform. "
        "Tools: query VictoriaMetrics metrics, read pod logs, check K8s status, "
        "run PostgreSQL diagnostics, calculate SLO burn rates, read runbooks, "
        "and execute auto-remediation actions."
    ),
)

for reg in [reg_vm, reg_logs, reg_k8s, reg_pg, reg_slo, reg_runbook, reg_remediation]:
    reg(mcp)


if __name__ == "__main__":
    webhook_thread = threading.Thread(target=webhook.run, daemon=True)
    webhook_thread.start()
    logger.info(f"Webhook server on :{config.WEBHOOK_PORT}")

    logger.info(f"MCP server starting ({config.MCP_TRANSPORT})")
    mcp.run(transport=config.MCP_TRANSPORT)
