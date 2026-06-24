# Demo Walkthrough

Step-by-step guide for deploying and running the full SRE EKS Observability Platform, including chaos scenarios that demonstrate L1 auto-remediation and L2 escalation.

## Prerequisites

Before starting, verify every tool is installed and configured:

```bash
# AWS CLI v2 — must return your account ID and IAM identity
aws sts get-caller-identity

# Pulumi CLI — local state backend, no Pulumi Cloud account needed
pulumi version   # tested with v3.x

# Container tools
docker --version          # Docker Desktop with buildx support
docker buildx version     # MUST have buildx for cross-platform builds

# Kubernetes tools
kubectl version --client
helm version

# Python 3.12+
python3 --version

# Git
git --version
```

**AWS account requirements:**
- Admin access (or at minimum: VPC, EKS, RDS, ECR, IAM, STS permissions)
- Region `ap-southeast-1` (configured in Pulumi stack; change in `Pulumi.dev.yaml` if needed)

**Budget:** approximately $6 for 3 hours of AWS resources. Cost breakdown:

| Resource | ~Cost/hour |
|----------|-----------|
| EKS control plane | $0.10 |
| 2x t3.medium nodes | $0.08 |
| RDS db.t4g.micro | $0.01 |
| NAT Gateway + data transfer | $0.05 |
| **Total** | **~$0.24/hour (~$5.80/day)** |

## Phase 1: Infrastructure (20 min)

### 1.1 Initialize Pulumi and install dependencies

```bash
cd infra
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Set up Pulumi local state (no Pulumi Cloud account needed):

```bash
pulumi login --local
export PULUMI_CONFIG_PASSPHRASE="your-passphrase"
pulumi stack init dev
```

If the `dev` stack already exists, select it instead:

```bash
pulumi stack select dev
```

### 1.2 Set the database password

```bash
pulumi config set --secret db-password "YourSecurePassword123!"
```

This stores the password encrypted in `Pulumi.dev.yaml`. All other config values have sensible defaults (see `infra/config.py`):
- Cluster name: `sre-demo`
- Node type: `t3.medium` (2 nodes)
- DB instance: `db.t4g.micro`
- Region: `ap-southeast-1`

### 1.3 Deploy infrastructure

```bash
pulumi up --yes
```

This takes approximately 15-20 minutes. Pulumi creates:

| Resource | Details |
|----------|---------|
| **VPC** | `10.0.0.0/16` CIDR, 2 AZs, public + private subnets, NAT Gateway |
| **EKS** | Kubernetes cluster `sre-demo` with 2x `t3.medium` managed nodes |
| **RDS** | PostgreSQL 17 on `db.t4g.micro` with pg_stat_statements enabled |
| **ECR** | 4 repositories under `sre-demo/` prefix (api-gateway, order-service, payment-service, mcp-server) |
| **IAM OIDC** | GitHub Actions federation for keyless CI/CD |

### 1.4 Get kubeconfig

```bash
pulumi stack output kubeconfig --show-secrets > /tmp/eks-demo-kubeconfig
export KUBECONFIG=/tmp/eks-demo-kubeconfig
```

Verify connectivity:

```bash
kubectl get nodes
```

Expected output: 2 nodes in `Ready` status.

```
NAME                                             STATUS   ROLES    AGE   VERSION
ip-10-0-x-x.ap-southeast-1.compute.internal      Ready    <none>   5m    v1.35.x
ip-10-0-y-y.ap-southeast-1.compute.internal      Ready    <none>   5m    v1.35.x
```

### 1.5 Install the EBS CSI driver (required for PersistentVolumeClaims)

EKS 1.35+ does not include the EBS CSI driver by default. VictoriaMetrics needs a PVC for storage, so this addon is required.

```bash
CLUSTER_NAME=$(pulumi stack output cluster_name)

# Get the node group name
NODEGROUP_NAME=$(aws eks list-nodegroups --cluster-name "$CLUSTER_NAME" --query 'nodegroups[0]' --output text)

# Get the node role name (strip the ARN prefix)
NODE_ROLE_ARN=$(aws eks describe-nodegroup --cluster-name "$CLUSTER_NAME" --nodegroup-name "$NODEGROUP_NAME" --query 'nodegroup.nodeRole' --output text)
NODE_ROLE_NAME=$(echo "$NODE_ROLE_ARN" | awk -F'/' '{print $NF}')

# Attach the EBS CSI driver policy to the node role
aws iam attach-role-policy \
  --role-name "$NODE_ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy

# Install the addon
aws eks create-addon --cluster-name "$CLUSTER_NAME" --addon-name aws-ebs-csi-driver
```

Wait for the addon to become active:

```bash
aws eks describe-addon --cluster-name "$CLUSTER_NAME" --addon-name aws-ebs-csi-driver --query 'addon.status'
```

Expected output: `"ACTIVE"`. This may take 1-2 minutes.

## Phase 2: Observability Stack (10 min)

### 2.1 Run the setup script

From the project root:

```bash
./scripts/setup.sh
```

This script performs 10 steps:

| Step | What it does |
|------|-------------|
| 0/9 | Exports kubeconfig from Pulumi stack output |
| 1/8 | Creates `observability` and `demo` namespaces |
| 2/8 | Installs VictoriaMetrics Operator via Helm |
| 3/8 | Applies VM CRDs: VMSingle (storage), VMAgent (scrape), VMAlertmanager, VMAlert |
| 4/8 | Installs OpenTelemetry Collector in gateway mode via Helm + HPA |
| 5/8 | Installs Vector as DaemonSet for log collection |
| 6/9 | Creates Grafana dashboard ConfigMap + installs Grafana via Helm |
| 7/9 | Deploys postgres_exporter with custom queries |
| 8/9 | Installs kube-state-metrics via Helm |
| 9/9 | Applies VMRule recording rules and alert definitions |

At the end, the script prints the Grafana admin password. Save it.

### 2.2 Verify everything is running

```bash
kubectl get pods -n observability
```

All pods should be `Running` or `Completed`. Key pods to look for:

```
NAME                                        READY   STATUS    RESTARTS
grafana-xxxxxxxxx-xxxxx                     1/1     Running   0
kube-state-metrics-xxxxxxxxx-xxxxx          1/1     Running   0
otel-collector-opentelemetry-collector-xxx  1/1     Running   0
postgres-exporter-xxxxxxxxx-xxxxx           1/1     Running   0
vector-xxxxx                                1/1     Running   0
vmagent-xxxxxxxxx-xxxxx                     1/1     Running   0
vmalertmanager-xxxxxxxxx-xxxxx              1/1     Running   0
vmalert-xxxxxxxxx-xxxxx                     1/1     Running   0
vmsingle-xxxxxxxxx-xxxxx                    1/1     Running   0
```

**Troubleshooting:** If `vmsingle` is stuck in `Pending`, the EBS CSI driver is likely not installed or the `gp2` StorageClass does not exist. Re-check Phase 1 Step 1.5.

## Phase 3: Build and Deploy Applications (10 min)

### 3.1 Build and push Docker images

```bash
./scripts/build-push.sh
```

This script:
1. Reads the AWS region from Pulumi output
2. Generates an image tag from the current git commit SHA
3. Authenticates to ECR (`aws ecr get-login-password`)
4. Builds and pushes 4 images: `api-gateway`, `order-service`, `payment-service`, `mcp-server`

**CRITICAL for Mac ARM (M1/M2/M3/M4) users:** The default `docker build` produces `arm64` images. EKS runs `amd64` nodes. If you see `exec format error` on pods, you need to build with `--platform linux/amd64`.

The `build-push.sh` script uses plain `docker build`. On Apple Silicon, modify the build command or build manually:

```bash
# Manual cross-platform build (run from project root)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(cd infra && source venv/bin/activate && pulumi stack output region)
ECR_REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
TAG=$(git rev-parse --short HEAD)

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

for svc in api-gateway order-service payment-service; do
  docker buildx build --platform linux/amd64 --push \
    -t "$ECR_REGISTRY/sre-demo/$svc:$TAG" apps/$svc/
done

docker buildx build --platform linux/amd64 --push \
  -t "$ECR_REGISTRY/sre-demo/mcp-server:$TAG" -f mcp-server/Dockerfile .
```

Note the image tag printed at the end -- you need it for the next step.

### 3.2 Update secrets with real RDS credentials

Get the RDS endpoint and password from Pulumi:

```bash
cd infra && source venv/bin/activate
DB_ENDPOINT=$(pulumi stack output db_endpoint)
DB_PASSWORD=$(pulumi stack output db_password --show-secrets)
echo "Endpoint: $DB_ENDPOINT"
echo "Password: $DB_PASSWORD"
```

Edit `k8s/base/db-secret.yaml` and replace the placeholders:
- `REPLACE_WITH_RDS_ENDPOINT` with the actual RDS endpoint (e.g., `demo-xxxxxxx.xxxxxxxxx.ap-southeast-1.rds.amazonaws.com`)
- `REPLACE_WITH_PASSWORD` with the actual password

### 3.3 Update Kustomize image references

Edit `k8s/overlays/production/kustomization.yaml` and replace the placeholders:
- `ACCOUNT_ID` with your AWS account ID
- `REGION` with `ap-southeast-1` (or your configured region)
- `REPLACE_WITH_TAG` with the git commit SHA tag from the build step

Example after replacement:

```yaml
images:
  - name: api-gateway
    newName: 123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/sre-demo/api-gateway
    newTag: a1b2c3d
```

### 3.4 Deploy applications

```bash
kubectl apply -k k8s/overlays/production/
```

### 3.5 Verify deployment

```bash
kubectl get pods -n demo
```

Expected: all pods `Running` with `1/1` ready.

```
NAME                                READY   STATUS    RESTARTS
api-gateway-xxxxxxxxx-xxxxx        1/1     Running   0
order-service-xxxxxxxxx-xxxxx      1/1     Running   0
payment-service-xxxxxxxxx-xxxxx    1/1     Running   0
mcp-server-xxxxxxxxx-xxxxx         1/1     Running   0
```

Test the API gateway:

```bash
kubectl port-forward svc/api-gateway -n demo 8080:8080 &
curl http://localhost:8080/healthz
```

Expected response:

```json
{"status": "ok"}
```

Kill the background port-forward when done: `kill %1`

## Phase 4: Load Test and Dashboards (5 min)

### 4.1 Start port forwarding for all services

```bash
./scripts/port-forward.sh
```

This opens:
- **Grafana:** http://localhost:3000 (login: `admin` / password from setup output)
- **VictoriaMetrics:** http://localhost:8429
- **API Gateway:** http://localhost:8080
- **MCP Server:** http://localhost:8090

### 4.2 Run the load test

In a separate terminal:

```bash
./scripts/load-test.sh 300 5 "http://localhost:8080/order"
```

Arguments: `duration_seconds rps target_url`

This sends 5 requests per second for 5 minutes to the `/order` endpoint, which exercises the full api-gateway -> order-service -> payment-service -> PostgreSQL chain.

### 4.3 Observe Grafana dashboards

Wait 2-3 minutes for metrics to populate, then open Grafana at http://localhost:3000.

Three dashboards are provisioned:

| Dashboard | What it shows |
|-----------|-------------|
| **SLO Overview** | Error budget burn rate, availability SLI, latency percentiles |
| **Service Health** | Per-service request rate, error rate, latency histograms |
| **PostgreSQL Overview** | Connection count, slow queries, table stats, lock activity |

**Note:** If dashboard panels show "Loading plugin panel" instead of data, the file-based provisioning may have failed. Import dashboards manually via the Grafana API:

```bash
for dashboard in observability/grafana/dashboards/*.json; do
  curl -s -X POST http://admin:admin@localhost:3000/api/dashboards/db \
    -H "Content-Type: application/json" \
    -d "{\"dashboard\": $(cat "$dashboard"), \"overwrite\": true}"
done
```

## Phase 5: Chaos Scenarios

Each scenario injects a fault into the `payment-service` (which exposes chaos endpoints on port 8082) or directly into the Kubernetes deployment. The MCP server's webhook receiver decides whether to auto-remediate (L1) or escalate (L2).

**Prerequisite:** Ensure port-forwarding is active (`./scripts/port-forward.sh`) and the load test is running so metrics are being generated.

---

### Scenario 1: Latency Injection

**Simulates:** Network degradation or slow upstream dependency causing high API response times.

**Inject:**

```bash
./scripts/chaos/inject-latency.sh 2000
```

This calls the payment-service chaos endpoint to add a 2000ms artificial delay to every request.

**What to observe:**
- **Grafana SLO Overview:** p99 latency spikes above the 500ms SLO target
- **Grafana Service Health:** Latency histogram shifts right for payment-service
- **VMAlert:** `SLOBurnRateWarning` or `SLOBurnRateCritical` fires if the burn rate exceeds 6x or 14.4x respectively

**Expected outcome:** L2 escalation. Latency issues require human judgment to diagnose root cause (network, dependency, query performance). The MCP server webhook sends a notification with runbook link.

**Reset:**

```bash
./scripts/chaos/inject-latency.sh 0
```

---

### Scenario 2: Error Rate Spike

**Simulates:** Upstream dependency failure causing 5xx responses from the payment service.

**Inject:**

```bash
./scripts/chaos/inject-errors.sh 30
```

This configures 30% of payment-service requests to return HTTP 500 errors.

**What to observe:**
- **Grafana SLO Overview:** Availability SLI drops below 99.5% target, error budget burns rapidly
- **Grafana Service Health:** Error rate spikes for payment-service, propagates to api-gateway
- **VMAlert:** `SLOBurnRateCritical` fires (14.4x burn over 5m AND 1h windows) if error rate is sustained

**Expected outcome:** L2 escalation. Error spikes require root cause analysis (bad deploy, dependency outage, data issue). The webhook payload includes the alert name, severity, and a link to the relevant runbook.

**Reset:**

```bash
./scripts/chaos/inject-errors.sh 0
```

---

### Scenario 3: PostgreSQL Connection Exhaustion

**Simulates:** Connection leak or sudden traffic spike exhausting the PostgreSQL connection pool.

**Inject:**

```bash
./scripts/chaos/pg-connection-flood.sh 80
```

This opens 80 idle connections to PostgreSQL via the payment-service, pushing connection usage above the 80% threshold of `max_connections` (100).

**What to observe:**
- **Grafana PostgreSQL Overview:** Connection count spikes to near the limit
- **VMAlert:** `PostgreSQLConnectionsNearLimit` fires after 5 minutes above 80%
- **MCP Server logs:** L1 auto-remediation triggered

**Expected outcome:** L1 auto-remediation. The MCP server's `execute_remediation` tool runs `pg_terminate_backend()` to kill idle-in-transaction connections older than 5 minutes. Connection count drops back to normal.

**Verify remediation:**

```bash
kubectl logs -n demo deploy/mcp-server --tail=20 | grep -i "terminated"
```

**Reset:** Automatic. The MCP server kills the idle connections. If they persist, restart the payment-service pod:

```bash
kubectl rollout restart deployment/payment-service -n demo
```

---

### Scenario 4: Bad Deployment (CrashLoopBackOff)

**Simulates:** A broken image is deployed, causing pods to crash repeatedly.

**Inject:**

```bash
./scripts/chaos/deploy-broken.sh
```

This replaces the `payment-service` container image with `busybox:latest`, which lacks the Python runtime and immediately exits, triggering `CrashLoopBackOff`.

**What to observe:**
- **kubectl:** `kubectl get pods -n demo -w` shows payment-service pods cycling through CrashLoopBackOff
- **VMAlert:** `PodCrashLooping` fires after 3+ restarts in 15 minutes
- **MCP Server logs:** L1 auto-remediation triggered

**Expected outcome:** L1 auto-remediation. The MCP server's `execute_remediation` tool runs `kubectl rollout undo deployment/payment-service -n demo`, which rolls back to the previous working image.

**Verify rollback:**

```bash
kubectl rollout history deployment/payment-service -n demo
kubectl get pods -n demo -l app.kubernetes.io/name=payment-service
```

The pods should return to `Running` state with the previous image.

**Reset:** Automatic via rollback.

---

### Scenario 5: Slow PostgreSQL Queries

**Simulates:** A rogue query or missing index causing slow database performance.

**Inject:**

```bash
./scripts/chaos/pg-slow-query.sh 30
```

This triggers 30 seconds of artificially slow queries via the payment-service chaos endpoint.

**What to observe:**
- **Grafana PostgreSQL Overview:** Mean query execution time spikes
- **VMAlert:** `PostgreSQLSlowQueries` fires after mean execution time exceeds 1000ms for 5 minutes

**Expected outcome:** L2 escalation. Slow queries need human analysis (missing indexes, query optimization, lock contention).

**Reset:** Automatic after the configured duration (30s default).

## Phase 6: Cleanup

### 6.1 Destroy everything

```bash
./scripts/destroy.sh
```

This script performs a 4-step teardown:
1. Deletes Kubernetes application manifests (`kubectl delete -k`)
2. Uninstalls Helm releases (Grafana, Vector, OTel Collector, VMOperator)
3. Cleans ECR repositories (batch-deletes all images)
4. Runs `pulumi destroy --yes` to tear down all AWS infrastructure

The script prompts for confirmation before proceeding.

### 6.2 Verify cleanup

Check the AWS Console to confirm no resources remain:

- **EKS:** No clusters in `ap-southeast-1`
- **RDS:** No database instances
- **ECR:** No repositories under `sre-demo/`
- **VPC:** No VPCs tagged `Project: sre-eks-observability`
- **IAM:** No OIDC provider for `token.actions.githubusercontent.com` (if this was its only consumer)
- **NAT Gateway:** Verify no lingering NAT Gateways (these accrue hourly charges)
- **Elastic IPs:** Release any orphaned EIPs associated with the NAT Gateway

### 6.3 Clean up local files

```bash
rm -f /tmp/eks-demo-kubeconfig
unset KUBECONFIG
```

**Expected total cost:** approximately $6 for a 3-hour session.

## CI/CD Verification

After completing the manual deploy, you can set up the GitHub Actions pipeline for automated CI/CD. See [docs/ci-cd-setup.md](ci-cd-setup.md) for the full guide.

Quick summary:

```bash
# Get the OIDC role ARN from Pulumi
cd infra && source venv/bin/activate
ROLE_ARN=$(PULUMI_CONFIG_PASSPHRASE="your-passphrase" pulumi stack output github_actions_role_arn)

# Set it as a GitHub Actions secret (the only secret needed)
gh secret set AWS_DEPLOY_ROLE_ARN --body "$ROLE_ARN"

# Push to main to trigger the pipeline
git push origin main

# Watch the pipeline run
gh run watch
```

The pipeline has 4 jobs: path-filter detection, lint (Hadolint + Ruff + yamllint), build-push (Docker + ECR + Trivy), and deploy (Kustomize + kubectl).

## Quick Reference: All Commands

```bash
# Phase 1: Infrastructure
cd infra && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pulumi login --local
export PULUMI_CONFIG_PASSPHRASE="your-passphrase"
pulumi stack init dev
pulumi config set --secret db-password "YourPassword!"
pulumi up --yes

# Phase 1.5: kubeconfig + EBS CSI
pulumi stack output kubeconfig --show-secrets > /tmp/eks-demo-kubeconfig
export KUBECONFIG=/tmp/eks-demo-kubeconfig
CLUSTER_NAME=$(pulumi stack output cluster_name)
aws eks create-addon --cluster-name "$CLUSTER_NAME" --addon-name aws-ebs-csi-driver

# Phase 2: Observability
./scripts/setup.sh

# Phase 3: Build + Deploy
./scripts/build-push.sh                        # edit build-push.sh for buildx on ARM
# edit k8s/base/db-secret.yaml with real RDS values
# edit k8s/overlays/production/kustomization.yaml with real ECR+tag values
kubectl apply -k k8s/overlays/production/

# Phase 4: Load test
./scripts/port-forward.sh                      # terminal 1
./scripts/load-test.sh 300 5                   # terminal 2

# Phase 5: Chaos
./scripts/chaos/inject-latency.sh 2000         # scenario 1
./scripts/chaos/inject-errors.sh 30            # scenario 2
./scripts/chaos/pg-connection-flood.sh 80      # scenario 3
./scripts/chaos/deploy-broken.sh               # scenario 4
./scripts/chaos/pg-slow-query.sh 30            # scenario 5

# Phase 6: Cleanup
./scripts/destroy.sh
```
