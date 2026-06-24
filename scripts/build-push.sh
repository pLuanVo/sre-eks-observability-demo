#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/infra"
source venv/bin/activate
export PULUMI_CONFIG_PASSPHRASE="${PULUMI_CONFIG_PASSPHRASE:-sre-demo-2026}"
REGION=$(pulumi stack output region 2>/dev/null || echo "ap-southeast-1")
TAG=$(git -C "$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || echo "latest")

SERVICES=(api-gateway order-service payment-service mcp-server)

echo "=== Building and pushing images (tag: $TAG) ==="

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

for svc in "${SERVICES[@]}"; do
  REPO="$ECR_REGISTRY/sre-demo/$svc"
  echo "Building $svc (linux/amd64)..."

  if [ "$svc" = "mcp-server" ]; then
    docker buildx build --platform linux/amd64 --push \
      -t "$REPO:$TAG" -f "$PROJECT_DIR/mcp-server/Dockerfile" "$PROJECT_DIR"
  else
    docker buildx build --platform linux/amd64 --push \
      -t "$REPO:$TAG" "$PROJECT_DIR/apps/$svc/"
  fi
done

echo ""
echo "=== All images pushed ==="
echo "Tag: $TAG"
echo "Registry: $ECR_REGISTRY"
