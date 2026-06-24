#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== SRE EKS Observability Platform Setup ==="

echo "[0/9] Configuring kubectl..."
cd "$PROJECT_DIR/infra"
source venv/bin/activate
PULUMI_CONFIG_PASSPHRASE="${PULUMI_CONFIG_PASSPHRASE:-sre-demo-2026}" \
  pulumi stack output kubeconfig --show-secrets > /tmp/eks-demo-kubeconfig
export KUBECONFIG=/tmp/eks-demo-kubeconfig
kubectl cluster-info

echo "[1/8] Creating namespaces..."
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace demo --dry-run=client -o yaml | kubectl apply -f -

echo "[2/8] Installing VictoriaMetrics Operator..."
helm repo add vm https://victoriametrics.github.io/helm-charts/ 2>/dev/null || true
helm repo update vm
helm upgrade --install vmoperator vm/victoria-metrics-operator \
  --namespace observability \
  --values "$PROJECT_DIR/observability/victoriametrics/values.yaml" \
  --wait --timeout 5m

echo "    Waiting for vmoperator CRDs..."
kubectl wait --for=condition=Established crd/vmsingles.operator.victoriametrics.com --timeout=60s
kubectl wait --for=condition=Established crd/vmagents.operator.victoriametrics.com --timeout=60s

echo "[3/8] Applying VictoriaMetrics CRDs..."
kubectl apply -f "$PROJECT_DIR/observability/victoriametrics/vmsingle.yaml"
kubectl apply -f "$PROJECT_DIR/observability/victoriametrics/vmagent.yaml"
kubectl apply -f "$PROJECT_DIR/observability/victoriametrics/vmalertmanager.yaml"
kubectl apply -f "$PROJECT_DIR/observability/victoriametrics/vmalert.yaml"

echo "[4/8] Installing OpenTelemetry Collector..."
helm repo add otel https://open-telemetry.github.io/opentelemetry-helm-charts 2>/dev/null || true
helm repo update otel
helm upgrade --install otel-collector otel/opentelemetry-collector \
  --namespace observability \
  --values "$PROJECT_DIR/observability/otel-collector/values.yaml" \
  --wait --timeout 5m
kubectl apply -f "$PROJECT_DIR/observability/otel-collector/hpa.yaml"

echo "[5/8] Installing Vector..."
helm repo add vector https://helm.vector.dev 2>/dev/null || true
helm repo update vector
helm upgrade --install vector vector/vector \
  --namespace observability \
  --values "$PROJECT_DIR/observability/vector/values.yaml" \
  --wait --timeout 3m

echo "[6/9] Installing Grafana..."
helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
helm repo update grafana
kubectl create configmap grafana-dashboards \
  --namespace observability \
  --from-file="$PROJECT_DIR/observability/grafana/dashboards/" \
  --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install grafana grafana/grafana \
  --namespace observability \
  --values "$PROJECT_DIR/observability/grafana/values.yaml" \
  --wait --timeout 5m

echo "[7/9] Deploying postgres_exporter..."
kubectl apply -f "$PROJECT_DIR/observability/postgres-exporter/queries.yaml"
kubectl apply -f "$PROJECT_DIR/observability/postgres-exporter/deployment.yaml"

echo "[8/9] Installing kube-state-metrics..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo update prometheus-community
helm upgrade --install kube-state-metrics prometheus-community/kube-state-metrics \
  --namespace observability \
  --set prometheus.monitor.enabled=false \
  --wait --timeout 3m

echo "[9/9] Applying recording rules + alerts..."
kubectl apply -f "$PROJECT_DIR/observability/rules/recording-rules.yaml"
kubectl apply -f "$PROJECT_DIR/observability/rules/alerts.yaml"

echo ""
echo "=== Setup complete ==="
GRAFANA_PASS=$(kubectl get secret grafana -n observability -o jsonpath="{.data.admin-password}" | base64 -d)
echo "Grafana admin password: $GRAFANA_PASS"
echo "Run './scripts/port-forward.sh' to access services locally."
