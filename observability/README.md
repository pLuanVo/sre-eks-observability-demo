# Observability Stack

Deploy order (each step depends on the previous):

1. **VictoriaMetrics Operator** — `helm install vmoperator vm/victoria-metrics-operator -f victoriametrics/values.yaml -n observability`
2. **VMSingle** — `kubectl apply -f victoriametrics/vmsingle.yaml` (time-series storage)
3. **VMAgent** — `kubectl apply -f victoriametrics/vmagent.yaml` (metric scraping)
4. **VMAlert + VMAlertmanager** — `kubectl apply -f victoriametrics/vmalert.yaml -f victoriametrics/vmalertmanager.yaml`
5. **Recording Rules + Alerts** — `kubectl apply -f rules/`
6. **OTel Collector** — `helm install otel-collector open-telemetry/opentelemetry-collector -f otel-collector/values.yaml -n observability`
7. **Vector** — `helm install vector vector/vector -f vector/values.yaml -n observability`
8. **Grafana** — `helm install grafana grafana/grafana -f grafana/values.yaml -n observability`
9. **kube-state-metrics** — `helm install kube-state-metrics prometheus-community/kube-state-metrics -n observability`
10. **postgres-exporter** — `kubectl apply -f postgres-exporter/`

## Component Overview

| Component | Role | Port |
|-----------|------|------|
| VMSingle | Time-series database (Prometheus-compatible) | 8429 |
| VMAgent | Metric scraping and remote write | 8429 |
| VMAlert | Alert rule evaluation | 8880 |
| VMAlertmanager | Alert routing and notification | 9093 |
| OTel Collector | OTLP receiver, metric/trace pipeline | 4317, 4318 |
| Vector | Log collection and transformation (DaemonSet) | — |
| Grafana | Dashboard visualization | 3000 |
| kube-state-metrics | Kubernetes object metrics | 8080 |
| postgres-exporter | PostgreSQL metrics via custom queries | 9187 |
