#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Destroying all AWS resources ==="
echo "WARNING: This will delete the EKS cluster, RDS, and all associated resources."
read -p "Are you sure? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
  echo "Aborted."
  exit 0
fi

export KUBECONFIG=/tmp/eks-demo-kubeconfig

echo "[1/4] Cleaning up K8s resources..."
kubectl delete -k "$PROJECT_DIR/k8s/overlays/production/" --ignore-not-found 2>/dev/null || true

echo "[2/4] Removing Helm releases..."
for release in grafana vector otel-collector vmoperator; do
  helm uninstall "$release" -n observability 2>/dev/null || true
done

echo "[3/4] Cleaning ECR repositories..."
cd "$PROJECT_DIR/infra"
source venv/bin/activate
export PULUMI_CONFIG_PASSPHRASE="${PULUMI_CONFIG_PASSPHRASE:-sre-demo-2026}"
REGION=$(pulumi stack output region 2>/dev/null || echo "ap-southeast-1")
for repo in api-gateway order-service payment-service mcp-server; do
  echo "  Cleaning sre-demo/$repo..."
  IMAGE_IDS=$(aws ecr list-images --repository-name "sre-demo/$repo" --query 'imageIds[*]' --output json --region "$REGION" 2>/dev/null || echo "[]")
  if [ "$IMAGE_IDS" != "[]" ] && [ -n "$IMAGE_IDS" ]; then
    aws ecr batch-delete-image --repository-name "sre-demo/$repo" --image-ids "$IMAGE_IDS" --region "$REGION" 2>/dev/null || true
  fi
done

echo "[4/4] Destroying infrastructure..."
pulumi destroy --yes

echo ""
echo "=== All resources destroyed ==="
echo "Verify in AWS Console that no resources remain."
