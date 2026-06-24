"""Remediation tool — L1 auto-fix and L2 escalation actions."""

import json
import logging
import subprocess

import psycopg2
import requests

import config

logger = logging.getLogger("sre-mcp.remediation")


def register(mcp):
    @mcp.tool()
    def execute_remediation(action: str, target: str, params: dict = {}) -> str:
        """Execute a remediation action.

        Args:
            action: Action type — 'rollback_deployment', 'restart_pod', 'pg_kill_idle',
                    'pg_kill_query', 'scale_deployment', 'escalate'
            target: Target resource (deployment name, pod name, etc.)
            params: Additional parameters (e.g. {'replicas': 3} for scale, {'pid': 123} for pg_kill_query)
        """
        ns = config.K8S_NAMESPACE

        if action == "rollback_deployment":
            return _run_kubectl(f"rollout undo deployment/{target} -n {ns}")

        elif action == "restart_pod":
            return _run_kubectl(f"delete pod {target} -n {ns}")

        elif action == "scale_deployment":
            replicas = params.get("replicas", 3)
            return _run_kubectl(f"scale deployment/{target} --replicas={replicas} -n {ns}")

        elif action == "pg_kill_idle":
            return _pg_kill_idle()

        elif action == "pg_kill_query":
            pid = params.get("pid")
            if not pid:
                return "Error: 'pid' parameter required for pg_kill_query"
            return _pg_kill_query(int(pid))

        elif action == "escalate":
            return _escalate(target, params)

        else:
            available = "rollback_deployment, restart_pod, pg_kill_idle, pg_kill_query, scale_deployment, escalate"
            return f"Unknown action: {action}. Available: {available}"


def _run_kubectl(args):
    try:
        result = subprocess.run(
            f"kubectl {args}".split(),
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            logger.info(f"kubectl {args}: success")
            return f"Success: kubectl {args}\n{result.stdout}"
        return f"Error: kubectl {args}\n{result.stderr}"
    except Exception as e:
        return f"Error running kubectl: {e}"


def _pg_kill_idle():
    try:
        conn = psycopg2.connect(config.pg_dsn())
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE state = 'idle in transaction' "
                "AND query_start < now() - interval '5 minutes' "
                "AND pid != pg_backend_pid()"
            )
            terminated = cur.rowcount
        conn.commit()
        conn.close()
        logger.info(f"Terminated {terminated} idle-in-transaction connections")
        return f"Terminated {terminated} idle-in-transaction connections (>5 min)"
    except Exception as e:
        return f"Error killing idle connections: {e}"


def _pg_kill_query(pid):
    try:
        conn = psycopg2.connect(config.pg_dsn())
        with conn.cursor() as cur:
            cur.execute("SELECT pg_cancel_backend(%s)", (pid,))
            result = cur.fetchone()[0]
        conn.close()
        logger.info(f"Cancelled query on PID {pid}: {result}")
        return f"pg_cancel_backend({pid}): {result}"
    except Exception as e:
        return f"Error cancelling query: {e}"


def _escalate(alert_name, context):
    payload = {
        "level": "L2",
        "alert": alert_name,
        "context": context,
        "action": "human_review_required",
    }
    try:
        resp = requests.post(
            config.WEBHOOK_URL,
            json=payload,
            timeout=5,
        )
        logger.info(f"Escalated {alert_name} to webhook: {resp.status_code}")
        return f"Escalated to webhook: {json.dumps(payload, indent=2)}"
    except Exception as e:
        logger.warning(f"Webhook escalation failed: {e}")
        return f"Escalation payload (webhook failed):\n{json.dumps(payload, indent=2)}"
