"""Flask webhook server — receives VMAlertmanager alerts, dispatches L1/L2."""

import logging
import os

from flask import Flask, request as flask_request, jsonify

import config

logger = logging.getLogger("sre-mcp.webhook")

app = Flask("sre-webhook")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "healthy"}), 200


@app.route("/webhook", methods=["POST"])
def alert_webhook():
    """Receive VMAlertmanager webhook, decide L1 auto-fix or L2 escalate."""
    payload = flask_request.get_json(silent=True) or {}
    alerts = payload.get("alerts", [])

    for alert in alerts:
        if alert.get("status") != "firing":
            continue

        name = alert.get("labels", {}).get("alertname", "unknown")
        runbook_url = alert.get("annotations", {}).get("runbook", "")
        logger.info(f"Alert received: {name}, runbook: {runbook_url}")

        runbook_name = runbook_url.split("/")[-1].replace(".md", "") if runbook_url else ""

        if runbook_name:
            try:
                runbook_path = os.path.join(config.RUNBOOK_DIR, f"{runbook_name}.md")
                with open(runbook_path) as f:
                    content = f.read()
                if "AUTO-REMEDIATION: ELIGIBLE" in content:
                    logger.info(f"L1: Auto-remediation eligible for {name}")
                    return jsonify({"level": "L1", "alert": name, "action": "auto-remediate"})
            except FileNotFoundError:
                pass

        logger.info(f"L2: Escalating {name} to webhook")
        return jsonify({"level": "L2", "alert": name, "action": "escalated"})

    return jsonify({"status": "ok"})


def run(host="0.0.0.0", port=None):
    """Start the webhook Flask server."""
    port = port or config.WEBHOOK_PORT
    app.run(host=host, port=port, debug=False)
