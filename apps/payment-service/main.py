import json
import logging
import os
import random
import threading
import time

import psycopg2
from flask import Flask, jsonify, request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

SERVICE_NAME = "payment-service"

logging.basicConfig(
    format=json.dumps({
        "timestamp": "%(asctime)s",
        "level": "%(levelname)s",
        "service": SERVICE_NAME,
        "message": "%(message)s",
    }),
    level=logging.INFO,
)
logger = logging.getLogger(SERVICE_NAME)

resource = Resource.create({"service.name": SERVICE_NAME})
provider = TracerProvider(resource=resource)
otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector.observability:4317")
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(SERVICE_NAME)

Psycopg2Instrumentor().instrument()

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests",
    ["method", "endpoint", "code", "service"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "Request duration",
    ["method", "endpoint", "service"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

DB_DSN = os.environ.get("DATABASE_URL", "")

chaos_config = {
    "latency_ms": 0,
    "error_rate": 0,
    "pg_flood_connections": [],
    "pg_slow_active": False,
}


def get_db():
    return psycopg2.connect(DB_DSN)


@app.before_request
def before():
    request._start_time = time.time()


@app.after_request
def after(response):
    if hasattr(request, "_start_time") and request.path not in ("/metrics", "/healthz", "/chaos/status"):
        duration = time.time() - request._start_time
        REQUEST_COUNT.labels(request.method, request.path, response.status_code, SERVICE_NAME).inc()
        REQUEST_DURATION.labels(request.method, request.path, SERVICE_NAME).observe(duration)
    return response


@app.route("/pay", methods=["POST"])
def pay():
    with tracer.start_as_current_span("process-payment"):
        if chaos_config["latency_ms"] > 0:
            time.sleep(chaos_config["latency_ms"] / 1000.0)

        if chaos_config["error_rate"] > 0:
            if random.randint(1, 100) <= chaos_config["error_rate"]:
                logger.error("Injected payment error")
                return jsonify({"error": "Payment processing failed (injected)"}), 500

        data = request.get_json(silent=True) or {}
        order_id = data.get("order_id")
        amount = data.get("amount", 0)

        try:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO payments (order_id, amount, status, transaction_id) VALUES (%s, %s, %s, %s)",
                    (order_id, amount, "completed", f"txn-{random.randint(10000, 99999)}"),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB write failed: {e}")
            return jsonify({"error": str(e)}), 500

        return jsonify({"service": SERVICE_NAME, "status": "paid", "order_id": order_id}), 200


# --- Chaos endpoints ---

@app.route("/chaos/latency", methods=["POST"])
def set_latency():
    data = request.get_json()
    chaos_config["latency_ms"] = data.get("delay_ms", 0)
    logger.warning(f"Chaos: latency set to {chaos_config['latency_ms']}ms")
    return jsonify({"latency_ms": chaos_config["latency_ms"]})


@app.route("/chaos/errors", methods=["POST"])
def set_error_rate():
    data = request.get_json()
    chaos_config["error_rate"] = data.get("rate", 0)
    logger.warning(f"Chaos: error rate set to {chaos_config['error_rate']}%")
    return jsonify({"error_rate": chaos_config["error_rate"]})


@app.route("/chaos/pg-flood", methods=["POST"])
def pg_flood():
    """Open many idle connections to exhaust the PG connection pool."""
    count = request.get_json().get("count", 80)
    for _ in range(count):
        try:
            conn = psycopg2.connect(DB_DSN)
            chaos_config["pg_flood_connections"].append(conn)
        except Exception as e:
            logger.error(f"PG flood: connection failed at {len(chaos_config['pg_flood_connections'])}: {e}")
            break
    total = len(chaos_config["pg_flood_connections"])
    logger.warning(f"Chaos: opened {total} idle PG connections")
    return jsonify({"idle_connections": total})


@app.route("/chaos/pg-slow", methods=["POST"])
def pg_slow():
    """Inject slow queries in a background thread."""
    duration = request.get_json().get("duration_sec", 30)
    chaos_config["pg_slow_active"] = True

    def run_slow_queries():
        end = time.time() + duration
        while time.time() < end and chaos_config["pg_slow_active"]:
            try:
                conn = get_db()
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_sleep(3)")
                conn.close()
            except Exception:
                pass
            time.sleep(0.5)
        chaos_config["pg_slow_active"] = False

    threading.Thread(target=run_slow_queries, daemon=True).start()
    logger.warning(f"Chaos: slow queries active for {duration}s")
    return jsonify({"pg_slow_active": True, "duration_sec": duration})


@app.route("/chaos", methods=["DELETE"])
def reset_chaos():
    chaos_config["latency_ms"] = 0
    chaos_config["error_rate"] = 0
    chaos_config["pg_slow_active"] = False
    for conn in chaos_config["pg_flood_connections"]:
        try:
            conn.close()
        except Exception:
            pass
    chaos_config["pg_flood_connections"] = []
    logger.info("Chaos: all injection reset")
    return jsonify({"status": "all chaos reset"})


@app.route("/chaos/status")
def chaos_status():
    return jsonify({
        "latency_ms": chaos_config["latency_ms"],
        "error_rate": chaos_config["error_rate"],
        "pg_flood_connections": len(chaos_config["pg_flood_connections"]),
        "pg_slow_active": chaos_config["pg_slow_active"],
    })


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/healthz")
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8082)
