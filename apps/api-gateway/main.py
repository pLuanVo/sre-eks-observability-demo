import json
import logging
import os
import time

import psycopg2
import requests as http_requests
from flask import Flask, jsonify, request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

SERVICE_NAME = "api-gateway"

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
RequestsInstrumentor().instrument()

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests",
    ["method", "endpoint", "code", "service"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "Request duration",
    ["method", "endpoint", "service"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

ORDER_SERVICE_URL = os.environ.get("ORDER_SERVICE_URL", "http://order-service:8081")
DB_DSN = os.environ.get("DATABASE_URL", "")


def get_db():
    return psycopg2.connect(DB_DSN)


@app.before_request
def before():
    request._start_time = time.time()


@app.after_request
def after(response):
    if hasattr(request, "_start_time"):
        duration = time.time() - request._start_time
        endpoint = request.path
        REQUEST_COUNT.labels(request.method, endpoint, response.status_code, SERVICE_NAME).inc()
        REQUEST_DURATION.labels(request.method, endpoint, SERVICE_NAME).observe(duration)
    return response


@app.route("/")
def index():
    logger.info("Serving index")
    return jsonify({"service": SERVICE_NAME, "status": "ok"})


@app.route("/order")
def create_order():
    with tracer.start_as_current_span("create-order"):
        resp = http_requests.post(f"{ORDER_SERVICE_URL}/process", timeout=10)
        try:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO api_requests (path, method, status_code, duration_ms) VALUES (%s, %s, %s, %s)",
                    ("/order", "GET", resp.status_code, (time.time() - request._start_time) * 1000),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB write failed: {e}")
        return jsonify({"service": SERVICE_NAME, "order_result": resp.json()}), resp.status_code


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/healthz")
def health():
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
