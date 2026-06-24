# Technology Stack

A comprehensive reference for every technology powering the SRE EKS Observability Demo — a production-grade observability platform on Amazon EKS with AI-driven incident response.

---

## Infrastructure as Code — Pulumi (Python)

Pulumi is an Infrastructure as Code platform that uses general-purpose programming languages instead of domain-specific configuration files. This project uses the Python SDK (pulumi >= 3, pulumi-aws >= 6, pulumi-awsx >= 2, pulumi-eks >= 3) to define all AWS infrastructure, leveraging Python's type system, control flow, and package ecosystem for infrastructure definitions.

The primary architectural pattern is **ComponentResource** — Pulumi's abstraction for grouping related resources into reusable, encapsulated modules. The project defines 5 ComponentResource classes, each registered under the `sre:infra` namespace:

| ComponentResource | Key Resources | Outputs |
|---|---|---|
| `Vpc` (`sre:infra:Vpc`) | VPC (10.0.0.0/16), 2 AZs, public/private /24 subnets, single NAT gateway | `vpc_id`, `private_subnet_ids`, `public_subnet_ids` |
| `EksCluster` (`sre:infra:EksCluster`) | EKS cluster, managed node group (private subnets, no public IP), OIDC provider | `cluster_name`, `kubeconfig`, `node_security_group_id`, `oidc_provider_url/arn` |
| `RdsDatabase` (`sre:infra:RdsDatabase`) | PostgreSQL 17 instance, custom parameter group, security group (5432 from EKS only) | `endpoint`, `port`, `db_name` |
| `EcrRepos` (`sre:infra:EcrRepos`) | 4 ECR repositories with scan-on-push, lifecycle policies (keep last 10 images) | `repo_url` per service |
| `IamGithubOidc` (`sre:infra:IamGithubOidc`) | OIDC provider, IAM role with STS trust, EKS AccessEntry + ClusterAdmin policy | `github_actions_role_arn` |

Configuration is centralized through an `AppConfig` class that loads all values from `Pulumi.dev.yaml` (region, instance types, node count, database credentials) and provides consistent `base_tags` (`Project`, `Environment`, `ManagedBy`) across all resources. The stack name (`dev`) drives environment separation — the same codebase deploys to staging or production by switching stacks.

**Why Pulumi over Terraform**: Terraform's HCL is declarative but limited — no native loops with complex logic, no type-safe variable passing between modules, and state management requires separate backend configuration. Pulumi provides first-class Python: ComponentResource classes use constructors, properties, and inheritance for clean abstractions. Type checking catches misconfiguration at write time rather than plan time. The `pulumi_awsx` library provides high-level components (e.g., `awsx.ec2.Vpc` handles subnet CIDR calculation, NAT gateway placement, and route tables in a single call). Sharing configuration between infrastructure and application code eliminates the impedance mismatch of separate IaC languages.

**Production scaling path**: This demo uses a single stack with local state. At enterprise scale, the infrastructure splits into **micro-stacks** — networking, platform (EKS), data (RDS), and application stacks — connected via `StackReference` for cross-stack output sharing. State moves to Pulumi Cloud for team collaboration, state locking, and drift detection. Secrets management transitions from per-stack encryption to **Pulumi ESC** (Environments, Secrets, and Configuration) for centralized secret rotation and environment composition. Policy-as-code via CrossGuard enforces organizational guardrails (e.g., no public S3 buckets, required encryption).

---

## Container Orchestration — Amazon EKS

Amazon Elastic Kubernetes Service (EKS) is a managed Kubernetes control plane that eliminates the operational burden of etcd management, API server patching, and control plane high availability. AWS manages the control plane across multiple Availability Zones; the operator manages only the worker node groups and workloads.

This demo provisions a 2-node cluster (`t3.medium`) on private subnets with no public IP assignment, reducing attack surface. Worker nodes connect to the control plane through the VPC's NAT gateway. The cluster creates an OIDC provider that enables IAM Roles for Service Accounts (IRSA) — Kubernetes pods can assume AWS IAM roles without long-lived credentials.

**Namespace isolation**: Resources are separated into two namespaces with distinct concerns:

| Namespace | Purpose | Workloads |
|---|---|---|
| `demo` | Application workloads | api-gateway, order-service, payment-service, mcp-server, postgres-exporter, db-init job |
| `observability` | Monitoring infrastructure | VictoriaMetrics (VMSingle, VMAgent, VMAlert, VMAlertmanager), OTel Collector, Vector, Grafana, kube-state-metrics |

**Kustomize patterns**: The `k8s/` directory follows a base/overlay structure. The base layer (`k8s/base/`) defines all resources with development defaults — namespace `demo`, common label `app.kubernetes.io/part-of: sre-demo`, 2 replicas per service, HPA ranges of 2-5 pods. The staging overlay (`k8s/overlays/staging/`) patches replicas down to 1 and HPA ranges to 1-2 for cost reduction. The production overlay (`k8s/overlays/production/`) overrides image references to point at ECR repositories with SHA-tagged images. Each application has dedicated manifests for `Deployment`, `Service`, `HPA` (autoscaling/v2, 70% CPU target), and `PodDisruptionBudget` (`minAvailable: 1`).

**Security model**: A `demo-app` ServiceAccount with a scoped Role grants least-privilege access: get/list ConfigMaps and Secrets, get/list/delete Pods, get/list/patch Deployments and Deployments/scale. This enables the MCP server's remediation tools (pod restarts, deployment rollbacks, scaling) without cluster-wide permissions. NetworkPolicies enforce namespace boundaries — demo pods accept inbound traffic only from within the namespace or from the observability namespace on specific ports (8080-8082 for apps, 8090-8091 for MCP, 9187 for postgres-exporter). The observability namespace accepts OTLP traffic (4317, 4318) only from the demo namespace.

**Production scaling path**: Move from fixed-size node groups to **Karpenter** for bin-packing and right-sizing across instance families. Add multi-AZ node groups with topology spread constraints for zone-aware scheduling. Implement **Pod Identity** (the successor to IRSA) for simplified IAM integration. Layer **Istio** or **Cilium** service mesh for mTLS, traffic splitting, and L7 observability. For multi-cluster scenarios, use EKS Anywhere or fleet management with ArgoCD for GitOps-driven deployments across regions.

---

## Metrics & Monitoring — VictoriaMetrics

VictoriaMetrics is a high-performance, Prometheus-compatible time-series database designed for large-scale monitoring. It implements the Prometheus remote write API, supports PromQL (and its superset MetricsQL), and provides Kubernetes-native management through the **vmoperator** — a set of Custom Resource Definitions (CRDs) that declare the desired monitoring state and let the operator reconcile the actual cluster state.

**Why VictoriaMetrics over Prometheus**: Prometheus is the de facto standard for Kubernetes monitoring, but it has well-documented scaling limitations. VictoriaMetrics uses 3-5x less memory for the same cardinality through aggressive compression and cache-efficient data structures. Where Prometheus requires a separate Alertmanager, Thanos sidecar for long-term storage, and careful shard management, VictoriaMetrics provides a single-binary **VMSingle** for small-to-medium deployments or a sharded **VMCluster** for enterprise scale. The vmoperator manages the full lifecycle — creating StatefulSets, Services, and storage claims from CRD specs — eliminating the manual Helm chart tuning that Prometheus typically requires. MetricsQL extends PromQL with functions like `label_set()`, `range_quantile()`, and subquery optimizations that simplify complex SLI calculations.

**Components deployed in this demo**:

| Component | CRD | Configuration |
|---|---|---|
| **VMSingle** | `VMSingle/victoria-metrics` | 24h retention, 10Gi gp2 storage, dedup interval 15s, requests 200m/256Mi, limits 500m/512Mi |
| **VMAgent** | `VMAgent/vmagent` | 15s scrape interval, 1 replica, remote write to VMSingle:8429 |
| **VMAlert** | `VMAlert/vmalert` | Datasource + remote write/read to VMSingle, notifier to VMAlertmanager:9093 |
| **VMAlertmanager** | `VMAlertmanager/alertmanager` | Routes severity=critical\|warning to MCP webhook, group_wait 30s, repeat_interval 4h |

**Scrape configuration**: VMAgent defines 3 inline scrape jobs via Kubernetes service discovery:

1. **demo-pods** — `kubernetes_sd_configs` role `pod` in the `demo` namespace, filtered by the `prometheus.io/scrape: "true"` annotation. Port and path are dynamically resolved from `prometheus.io/port` and `prometheus.io/path` annotations on each pod. This automatically discovers the 3 Flask services (api-gateway:8080, order-service:8081, payment-service:8082) and the MCP server (8090).
2. **postgres-exporter** — `kubernetes_sd_configs` role `endpoints` in the `demo` namespace, filtered to the `postgres-exporter` service on port name `metrics` (9187).
3. **kube-state-metrics** — `kubernetes_sd_configs` role `endpoints` in the `observability` namespace, filtered to the `kube-state-metrics` service on port name `http`.

**Alert pipeline**: VMAgent scrapes targets every 15 seconds and writes to VMSingle. VMAlert evaluates recording rules (SLI aggregations) and alert rules against VMSingle's query API every 30 seconds. When an alert fires, VMAlert sends it to VMAlertmanager, which groups alerts by `alertname`, `namespace`, and `service`, waits 30 seconds for group completion, then dispatches to the MCP server's webhook endpoint at `http://mcp-server.demo:8091/webhook`. The `send_resolved: true` flag ensures the MCP server also receives resolution notifications for incident tracking.

**Production scaling path**: Replace VMSingle with **VMCluster** — a horizontally-scalable architecture with separate `vminsert` (write path), `vmselect` (read path), and `vmstorage` (persistence) components. Each component scales independently: add vmstorage nodes for capacity, vmselect nodes for query throughput, vminsert nodes for write ingestion. Enable deduplication across HA pairs. For long-term retention beyond local disk, configure object storage (S3) as a secondary retention tier. Multi-tenant environments use **vmauth** as a routing proxy to enforce per-tenant query isolation and rate limits.

---

## Distributed Tracing — OpenTelemetry Collector

The OpenTelemetry Collector is a vendor-neutral telemetry pipeline that receives, processes, and exports observability signals (metrics, traces, logs) in a standardized way. It implements the OTLP (OpenTelemetry Protocol) specification and acts as a centralized gateway between instrumented applications and backend storage systems, decoupling producers from consumers.

**Deployment architecture**: The collector runs in **gateway mode** as a single Deployment (1 replica, HPA 1-3 at 70% CPU) in the observability namespace. All three Flask applications send telemetry via the OpenTelemetry SDK to the collector's OTLP endpoints — gRPC on port 4317 and HTTP on port 4318. The collector processes the data and exports it to VictoriaMetrics.

**Pipeline configuration** — the collector defines two independent signal pipelines:

```
Metrics pipeline:  otlp receiver → memory_limiter → k8sattributes → batch → prometheusremotewrite exporter
Traces pipeline:   otlp receiver → memory_limiter → batch → debug exporter
```

| Stage | Component | Configuration |
|---|---|---|
| **Receivers** | `otlp` | gRPC on 0.0.0.0:4317, HTTP on 0.0.0.0:4318 |
| **Processors** | `memory_limiter` | check_interval 5s, limit_mib 400, spike_limit_mib 100 |
| | `k8sattributes` | Extracts `k8s.namespace.name`, `k8s.deployment.name`, `k8s.pod.name`, `k8s.pod.uid`, `k8s.node.name`; maps `service.name` from `app.kubernetes.io/name` pod label |
| | `batch` | send_batch_size 1024, timeout 5s |
| **Exporters** | `prometheusremotewrite` | Endpoint: VMSingle:8429/api/v1/write, resource_to_telemetry_conversion enabled |
| | `debug` | Verbosity: basic (traces only, for demo observability) |

The `memory_limiter` processor prevents OOM kills by rejecting data when memory approaches the 400 MiB limit — critical for a component that sits in the hot path of all telemetry. The `k8sattributes` processor enriches every span and metric with Kubernetes metadata by querying the K8s API, eliminating the need for applications to manually set resource attributes. A dedicated ClusterRole grants get/list/watch on pods, namespaces, deployments, and replicasets for this enrichment. The `batch` processor amortizes network overhead by buffering up to 1024 items or 5 seconds before flushing to exporters. The `resource_to_telemetry_conversion` flag on the Prometheus remote write exporter converts OTel resource attributes into Prometheus labels, ensuring that Kubernetes metadata appears as queryable dimensions in VictoriaMetrics.

**Production scaling path**: Replace the single gateway with an **agent + gateway topology**. Deploy OTel Collector as a DaemonSet (`agent` mode) on every node — agents handle local collection, sampling, and pre-aggregation with minimal network hops. Agents forward to a centralized gateway fleet (Deployment with HPA) that performs cross-node processing (tail-based sampling, span grouping) and exports to backends. For traces at scale, implement **tail-based sampling** on the gateway tier — buffer complete traces before making a sampling decision based on error status, latency, or service criticality. Add load balancing exporters to distribute writes across multiple backend instances. Route different signal types to purpose-built backends: metrics to VictoriaMetrics, traces to Tempo or Jaeger, logs to Loki.

---

## Log Collection — Vector

Vector is a high-performance observability data pipeline built in Rust by Datadog. It serves as a unified agent for collecting, transforming, and routing logs, metrics, and traces. Its standout feature is **VRL (Vector Remap Language)** — a type-safe, fail-safe expression language for data transformation that catches errors at compile time rather than silently dropping or corrupting log events at runtime.

**Why Vector over Fluentd/Fluent Bit**: Fluentd (Ruby) and Fluent Bit (C) are the traditional Kubernetes log collection choices, but they have meaningful operational drawbacks. Fluentd's Ruby runtime consumes 2-10x more memory than Vector for equivalent throughput. Fluent Bit is lighter but its plugin-based transform system lacks type safety — a misconfigured regex silently drops fields. Vector's Rust implementation provides memory safety without garbage collection pauses, and VRL transforms are validated at configuration load time. Vector also provides a native `kubernetes_logs` source that handles container log rotation, multi-line joining, and automatic metadata enrichment without external plugins.

**Deployment in this demo**: Vector runs as a **DaemonSet** (Agent role) with tolerations for all nodes (`operator: Exists`), ensuring every node has a log collector. Resource footprint is deliberately minimal: requests 50m CPU / 64Mi memory, limits 100m CPU / 128Mi memory.

| Pipeline Stage | Type | Configuration |
|---|---|---|
| **Source** | `kubernetes_logs` | Namespace selector: `kubernetes.io/metadata.name = demo` (only demo namespace) |
| **Transform** | `parse_json` (VRL remap) | Parses `.message` as JSON, extracts `.level`, `.service`, `.log_message`; falls back to `"info"` / `"unknown"` on parse failure; enriches with `.k8s_namespace`, `.k8s_pod`, `.k8s_container` from Kubernetes metadata |
| **Sink** | `console` | JSON encoding to stdout (demo-appropriate output) |

The VRL transform demonstrates a key pattern: structured log extraction with graceful degradation. The Flask applications emit JSON-structured logs (`{"timestamp": "...", "level": "...", "service": "...", "message": "..."}`), and VRL parses these into top-level fields for downstream filtering and routing. When a log line isn't valid JSON (e.g., gunicorn access logs, Python tracebacks), the transform falls back to safe defaults rather than dropping the event. The enrichment step copies Kubernetes metadata (namespace, pod name, container name) from Vector's automatic metadata fields into the event body, making every log line self-describing.

**Production scaling path**: Add an **aggregator tier** between the DaemonSet agents and storage backends. DaemonSet agents do lightweight collection and JSON parsing; aggregators (deployed as a StatefulSet or Deployment) handle expensive operations: PII redaction via VRL pattern matching, log-to-metric conversion, and multi-destination routing. Route logs to multiple sinks simultaneously — **S3** for cost-effective long-term archive, **Elasticsearch/OpenSearch** for full-text search, **Loki** for Grafana-native log correlation. VRL's `redact()` and `replace()` functions enable GDPR-compliant PII stripping before logs leave the cluster.

---

## Database — PostgreSQL 17 (Amazon RDS)

PostgreSQL 17 on Amazon RDS provides a managed relational database with automated patching, backups, and monitoring. RDS handles the undifferentiated heavy lifting — OS updates, minor version upgrades, storage management — while exposing PostgreSQL's full feature set including extensions and custom parameter tuning.

**Instance configuration**: The demo deploys a `db.t4g.micro` instance (ARM-based, burstable) with 20 GB gp3 storage, PostgreSQL engine version 17. The instance runs on private subnets with no public accessibility. The security group restricts inbound traffic to TCP port 5432 exclusively from the EKS node security group — no other network path can reach the database. For this demo, `skip_final_snapshot` is true, Multi-AZ is disabled, and backup retention is 0 days to minimize costs.

**Observability tuning** via custom parameter group (`postgres17`):

| Parameter | Value | Purpose |
|---|---|---|
| `shared_preload_libraries` | `pg_stat_statements` | Load the query statistics extension at server start |
| `pg_stat_statements.track` | `all` | Track queries from all users, including nested statements |
| `log_min_duration_statement` | `100` (ms) | Log any query taking longer than 100ms as a slow query |
| `max_connections` | `100` | Connection ceiling (monitored for exhaustion alerts) |
| `log_statement` | `ddl` | Log all DDL statements (CREATE, ALTER, DROP) for audit trail |

These parameters transform PostgreSQL from a black box into an observable system. `pg_stat_statements` provides per-query execution statistics (call count, total time, mean time, rows returned) that are essential for identifying performance regressions. The 100ms slow query log captures queries that are fast enough to avoid timeouts but slow enough to degrade tail latency.

**postgres_exporter** (v0.16.0): A dedicated exporter deployment translates PostgreSQL internal statistics into Prometheus metrics. It runs 4 custom query groups defined in a ConfigMap:

| Query Group | Source View | Key Metrics Exposed |
|---|---|---|
| `pg_stat_statements` | Top 20 queries by total_exec_time | `calls` (COUNTER), `total_time_ms` (COUNTER), `mean_time_ms` (GAUGE), `rows` (COUNTER) |
| `pg_stat_activity` | Connection states by user | `connections` (GAUGE) grouped by state (active, idle, idle in transaction) |
| `pg_locks` | Lock contention | `count` (GAUGE) grouped by mode and locktype |
| `pg_stat_user_tables` | Table-level statistics | 14 metrics: `seq_scan`, `idx_scan`, `n_live_tup`, `n_dead_tup`, `last_vacuum`, `last_autovacuum`, and more |

These metrics power the PostgreSQL Grafana dashboard and two alert rules: `PostgreSQLConnectionsNearLimit` (connection utilization > 80% for 5 minutes) and `PostgreSQLSlowQueries` (mean query time > 1000ms for 5 minutes). The connection exhaustion alert is paired with an auto-remediation runbook — the MCP server can autonomously terminate idle-in-transaction connections that have been stale for more than 5 minutes.

**Production scaling path**: Enable **Multi-AZ** for automatic failover (< 60 seconds). Add **read replicas** for read-heavy workloads, routing analytical queries away from the primary. Deploy **RDS Proxy** or **PgBouncer** for connection pooling — essential when running hundreds of pods that each maintain connection pools. Enable automated backups with point-in-time recovery (PITR) for disaster recovery. Use `pg_stat_statements` data to drive quarterly query optimization reviews, identifying candidates for index creation (as demonstrated in the sample postmortem where a missing index on `payments.created_at` caused a P2 latency incident).

---

## Visualization — Grafana

Grafana is the industry-standard platform for observability dashboards, providing a unified view across metrics, logs, and traces from multiple data sources. It supports over 150 data source plugins, alerting, annotations, and team-based access control. In this demo, Grafana connects to VictoriaMetrics using the native Prometheus data source type — VictoriaMetrics' full Prometheus API compatibility means no custom plugin is required.

**Deployment**: Grafana runs as a Helm release in the observability namespace on port 3000 (ClusterIP service). Anonymous access is enabled with the Viewer role for demo convenience. The VictoriaMetrics datasource is provisioned declaratively — configured as the default Prometheus-type datasource pointing to `http://vmsingle-victoria-metrics.observability:8429` in proxy mode.

**Three purpose-built dashboards** are provisioned via ConfigMap:

### 1. Service Health Dashboard (`service-health`)

Provides per-service operational visibility with a template variable (`$service`) populated from `label_values(http_requests_total, service)`:

| Panel | Visualization | Query | Unit |
|---|---|---|---|
| Request Rate | Timeseries | `sum(rate(http_requests_total{service="$service"}[5m]))` | req/s |
| Error Rate | Timeseries (red) | `sum(rate(http_requests_total{service="$service",code=~"5.."}[5m]))` | req/s |
| Latency Percentiles | Timeseries | p50, p95, p99 via `histogram_quantile` | seconds |
| Requests by Status Code | Timeseries | `sum by (code)(rate(http_requests_total{service="$service"}[5m]))` | req/s |
| Pod Status | Table | `kube_pod_status_phase{namespace="demo"}` | — |

### 2. SLO Overview Dashboard (`slo-overview`)

The primary SRE operational view, designed for at-a-glance SLO health assessment:

| Panel | Visualization | Key Thresholds |
|---|---|---|
| Availability SLI | Timeseries (percentunit) | Red line at 99.5% SLO target |
| p99 Latency | Timeseries | Yellow at 500ms, red at 1s |
| Error Budget Remaining | Gauge (percentunit) | Color-coded depletion |
| Burn Rate (5m/1h) | Stat | Yellow at 6x (warning), red at 14.4x (critical) |
| Request Rate by Service | Timeseries | — |

### 3. PostgreSQL Overview Dashboard (`pg-overview`)

Database-specific observability for capacity planning and performance troubleshooting:

| Panel | Visualization | Key Thresholds |
|---|---|---|
| Active Connections by State | Timeseries | Yellow at 80, red at 95 |
| Connection Utilization | Gauge (%) | Yellow at 70%, red at 90% |
| Max Connections | Stat | Reference value |
| Queries per Second | Timeseries | ops/s |
| Mean Query Time (top 10) | Bar gauge | seconds |
| Cache Hit Ratio | Stat | Yellow < 0.99, red < 0.90 |
| Dead Tuples | Timeseries | Vacuum effectiveness indicator |
| Locks Waiting | Stat | Yellow at 1, red at 5 |

**Production scaling path**: Migrate to **Grafana Cloud** or a dedicated Grafana instance with persistent storage. Adopt **Grafonnet** (Jsonnet library) or **Terraform Grafana provider** for dashboard-as-code, enabling version control, code review, and automated deployment of dashboard changes. Implement LDAP/SAML authentication with role-based folder permissions. Add Grafana's built-in alerting as a secondary alert path alongside VictoriaMetrics alerting for defense-in-depth. Explore Grafana's unified alerting to consolidate alert management across data sources.

---

## AI-Driven Incident Response — FastMCP

FastMCP implements the **Model Context Protocol (MCP)** — an open standard for connecting AI models to external tools and data sources. The MCP server exposes 7 diagnostic and remediation tools that an AI SRE agent (or human operator through an AI assistant) can invoke to investigate and resolve incidents. This transforms incident response from a purely reactive human process into an AI-augmented workflow where routine diagnostics and Level-1 fixes execute autonomously.

**Architecture**: Two servers run in the same container on separate ports:

| Server | Port | Protocol | Purpose |
|---|---|---|---|
| FastMCP Server | 8090 | SSE (Server-Sent Events) | Tool-based AI interaction via MCP protocol |
| Flask Webhook | 8091 | HTTP POST | VMAlertmanager alert ingestion |

### The 7 MCP Tools

| Tool | Parameters | What It Does |
|---|---|---|
| `query_metrics` | `query: str`, `time_range: str = "5m"` | Executes MetricsQL/PromQL against VMSingle API, returns up to 20 results with labels and values |
| `query_logs` | `service: str`, `level: str = ""`, `since: str = "15m"`, `tail: int = 50` | Reads pod logs via K8s API, filters by app label and optional log level, supports duration parsing (m/h/s) |
| `k8s_status` | `resource: str = "pods"`, `namespace: str = ""` | Shows pod phase + restart count, deployment ready/desired, or last 15 events sorted by timestamp |
| `pg_diagnostics` | `check: str` | Runs diagnostic queries: `connections` (by state), `slow_queries` (top 10 by mean time), `locks` (waiting), `table_stats` (scan/dead tuple stats) |
| `slo_burn_rate` | `service: str`, `slo_type: str = "availability"` | Calculates burn rate against 99.5% SLO target; thresholds: OK (<1x), WARNING (1-6x), CRITICAL (>6x) |
| `read_runbook` | `name: str = ""`, `list_all: bool = False` | Lists available runbooks or reads a specific runbook's markdown content |
| `execute_remediation` | `action: str`, `target: str`, `params: dict = {}` | Executes L1 actions: `rollback_deployment`, `restart_pod`, `scale_deployment`, `pg_kill_idle`, `pg_kill_query`, `escalate` |

### L1/L2 Decision Logic

The webhook handler implements automatic triage when VMAlertmanager fires an alert:

```
Alert received → Extract alertname + runbook annotation
  → Load runbook from /app/runbooks/
  → Scan for "AUTO-REMEDIATION: ELIGIBLE" marker
    → Found: L1 (execute automated fix via remediation tool)
    → Not found: L2 (escalate to human SRE)
```

Two of the 5 runbooks carry the auto-remediation marker: **pg-connection-exhaustion** (kills idle-in-transaction connections older than 5 minutes via `pg_terminate_backend()`) and **deployment-failure** (rolls back to the previous revision via `kubectl rollout undo`). The remaining 3 runbooks (high-latency, high-error-rate, pg-slow-queries) require human judgment and escalate to L2.

**Security model**: The MCP server runs with the `demo-app` ServiceAccount whose RBAC Role restricts Kubernetes operations to the `demo` namespace only — get/list/delete pods, get/list/patch deployments, get/list configmaps and secrets. The `execute_remediation` tool validates action names against a whitelist of 6 known actions and rejects unknown inputs.

**Production scaling path**: Deploy **domain-specific MCP servers** — separate servers for infrastructure diagnostics, database operations, and application-level tooling, each with its own RBAC scope. Add **approval gates** for destructive actions: L1 auto-remediation writes a proposed action to a queue, a human (or senior AI agent) approves/rejects within a time window, and only then does execution proceed. Implement comprehensive **audit logging** — every tool invocation, its parameters, the caller identity, and the result — for postmortem analysis and compliance. Add circuit breakers to prevent remediation loops (e.g., repeated rollbacks when the issue is in the latest *and* previous revision).

---

## CI/CD — GitHub Actions

GitHub Actions provides the CI/CD pipeline with native OIDC federation to AWS, eliminating the need for long-lived AWS credentials stored as repository secrets. The workflow is defined in `.github/workflows/ci.yml` and triggers on pushes to `main` (excluding `docs/*.md`), pull requests to `main`, and manual dispatch.

**Pipeline architecture** — 4 jobs with dependency-based execution:

```
changes (detect) ──→ lint (always) ──→ build-push (if apps changed) ──→ deploy (if build succeeds OR k8s changed)
```

| Job | Trigger Condition | Key Steps |
|---|---|---|
| **changes** | Always | `dorny/paths-filter@v3` detects changes in `apps/**`, `mcp-server/**`, `infra/**`, `k8s/**`, `observability/**` |
| **lint** | Always | Hadolint on 4 Dockerfiles, `ruff check` on Python (apps/ + mcp-server/), `yamllint -d relaxed` on K8s/observability/SRE manifests |
| **build-push** | Push + apps changed | OIDC auth, ECR login, build + push 4 images (SHA-tagged), Trivy vulnerability scan |
| **deploy** | build-push succeeds OR k8s changed | OIDC auth, kubeconfig update, sed image tags into production overlay, `kubectl apply -k`, rollout status verification (120s timeout) |

**OIDC federation flow**: GitHub Actions mints a JWT token containing the repository identity (`repo:pLuanVo/sre-eks-observability-demo:*`). The workflow calls `aws-actions/configure-aws-credentials@v4` with `role-to-assume`, which exchanges the JWT for temporary AWS credentials via `sts:AssumeRoleWithWebIdentity`. The IAM role's trust policy validates the OIDC provider thumbprint and restricts assumption to the specific repository. No AWS access keys are stored in GitHub Secrets — only the role ARN.

**Security scanning**: Trivy (`aquasecurity/trivy-action@master`) scans the `api-gateway` image for CRITICAL and HIGH severity vulnerabilities. The scan runs with `exit-code: "0"` (non-blocking) in this demo to prevent build failures from upstream base image CVEs. The scan results appear in the workflow logs for review.

**EKS deployment access**: The IAM role has an EKS `AccessEntry` (type STANDARD) with an `AccessPolicyAssociation` binding `AmazonEKSClusterAdminPolicy` at cluster scope. This grants the GitHub Actions runner full `kubectl` access without modifying the `aws-auth` ConfigMap — using EKS's newer access entry API instead of the legacy ConfigMap-based approach.

**Production scaling path**: Add **environment protection rules** with required reviewers for production deployments. Implement **parallel matrix builds** for multi-architecture images (amd64 + arm64). Enable Docker layer caching and pip dependency caching to reduce build times. Introduce **canary deployments** — deploy to a small percentage of pods, monitor error rates for 10 minutes, then proceed or rollback. Add DAST (Dynamic Application Security Testing) as a post-deploy verification step. Move Trivy to blocking mode (`exit-code: "1"`) once base images are pinned and regularly updated.

---

## SRE Practices

### SLO/SLI Framework

Service Level Objectives (SLOs) define the reliability targets that balance user experience against development velocity. This demo implements 3 SLOs defined in `sre/slo.yaml`:

| SLO | Target | Window | Error Budget | Key Metric |
|---|---|---|---|---|
| Availability | 99.5% | 30 days | 0.5% (3.6 hours) | Non-5xx ratio of `http_requests_total` |
| Latency | p99 < 500ms | 30 days | — | `histogram_quantile(0.99, http_request_duration_seconds_bucket)` |
| PG Availability | 99.9% | 30 days | 0.1% | PostgreSQL connection success rate |

Service Level Indicators (SLIs) are computed as recording rules evaluated every 30 seconds. The recording rule group `sli_recording_rules` pre-computes 9 metrics: `sli:availability:rate5m`, `sli:latency:rate5m` (p99), `sli:latency_p95:rate5m`, `sli:error_rate:rate5m`, `sli:request_rate:rate5m`, and burn rate calculations across 4 time windows (5m, 30m, 1h, 6h). Pre-computing SLIs as recording rules avoids expensive real-time aggregations on every dashboard load or alert evaluation.

### Multi-Window Burn Rate Alerting

Rather than alerting on simple thresholds (e.g., "error rate > 1%"), this demo implements **multi-window burn rate alerting** from the Google SRE Workbook. A burn rate of 1x means the error budget is consumed exactly at the expected rate over 30 days. Higher burn rates indicate accelerated budget consumption:

| Alert | Burn Rate | Windows | Duration | Severity | Budget Exhaustion |
|---|---|---|---|---|---|
| `SLOBurnRateCritical` | > 14.4x | 5m AND 1h | 2 min | Critical (P1) | ~2 days |
| `SLOBurnRateWarning` | > 6x | 30m AND 6h | 5 min | Warning (P2) | ~5 days |

The dual-window requirement (both short AND long window must exceed the threshold) eliminates false positives: a brief spike triggers the short window but not the long window, while a slow degradation triggers the long window but is caught early by the short window. Only sustained degradation across both windows fires an alert.

### Error Budget Policy

The error budget policy (`sre/error-budget-policy.yaml`) defines organizational responses as the budget depletes:

| Budget Consumed | Action | Impact |
|---|---|---|
| 50% | **Review** | SRE team reviews recent changes and error patterns |
| 75% | **Slow Down** | Reduce deployment frequency, require SRE review for all changes |
| 100% | **Feature Freeze** | Only reliability-improving changes allowed until budget recovers |

For latency SLOs, the thresholds are 75% (profile top-10 endpoints) and 100% (mandatory performance review before any deployment). Budget ownership sits with the SRE team, notifications go to `#sre-alerts`, and review cadence is weekly.

### Incident Response

The incident response framework (`sre/incident-response.md`) defines 4 severity levels with escalation paths:

| Severity | Trigger | Ack SLA | Triage SLA | Escalation |
|---|---|---|---|---|
| **P1** | Burn rate > 14.4x, budget ~2d | 5 min | 15 min | L0 → L1 → L2 → L3 |
| **P2** | Burn rate > 6x, budget ~5d | 15 min | 30 min | L0 → L1 → L2 |
| **P3** | Burn rate > 1x | 1 hour | — | L0 → L2 |
| **P4** | No SLO impact | Next business day | — | L2 |

Escalation levels: **L0** (VMAlert automated detection) → **L1** (MCP server auto-remediation for eligible scenarios) → **L2** (human SRE on-call, weekly rotation starting Monday 09:00 UTC+7) → **L3** (team lead + service owner for systemic issues).

### Runbooks

5 runbooks in `sre/runbooks/` provide structured response procedures:

| Runbook | Auto-Remediation | L1 Action |
|---|---|---|
| `high-latency.md` | Not eligible | — (requires human profiling) |
| `high-error-rate.md` | Not eligible | — (requires root cause analysis) |
| `pg-connection-exhaustion.md` | **Eligible** | `pg_terminate_backend()` on idle-in-transaction > 5 min |
| `pg-slow-queries.md` | Not eligible | — (requires query analysis) |
| `deployment-failure.md` | **Eligible** | `kubectl rollout undo` to previous revision |

Each runbook includes severity classification tables, time-boxed triage steps, diagnostic commands, and explicit escalation criteria. The `AUTO-REMEDIATION: ELIGIBLE` marker enables the MCP webhook handler to execute L1 fixes without human intervention.

### Postmortem Practice

A sample blameless postmortem (`sre/postmortems/2026-06-20-payment-latency.md`) documents a P2 incident: payment-service p99 latency spike caused by a missing index on `payments.created_at` during load testing. Duration: 25 minutes. Error budget consumed: 3.2%. Resolution: `CREATE INDEX CONCURRENTLY idx_payments_created_at ON payments(created_at)`. The postmortem follows a structured template: summary, impact, timeline, root cause, resolution, action items, lessons learned.

**Production scaling path**: These SRE practices scale from demo to enterprise without fundamental redesign. Burn rate thresholds are tuned per-service based on traffic volume and business criticality. Error budgets drive deployment velocity through automated policy enforcement (CI/CD gates that check remaining budget before allowing deploys). Runbooks evolve into living documents with execution metrics (mean time to remediate per runbook). Add ML-based anomaly detection as a complement to static threshold alerting — seasonal patterns in traffic mean that a "normal" error rate at 3 AM is different from 3 PM.

---

## Application Architecture — Flask Microservices

The demo application consists of 3 Flask microservices that form a request chain simulating an e-commerce order flow, plus a chaos engineering surface for reliability testing.

### Service Chain

```
Client → api-gateway (:8080) → order-service (:8081) → payment-service (:8082) → PostgreSQL (RDS)
```

| Service | Port | Endpoints | Database Tables |
|---|---|---|---|
| **api-gateway** | 8080 | `GET /` (health), `GET /order` (trigger chain) | `api_requests` |
| **order-service** | 8081 | `POST /process` (create order + call payment) | `orders` |
| **payment-service** | 8082 | `POST /pay` (process payment), chaos endpoints | `payments` |

All services share identical observability instrumentation:

- **Structured JSON logging**: Every log line contains `timestamp`, `level`, `service`, `message` — parseable by Vector's VRL transform
- **OpenTelemetry tracing**: `TracerProvider` with `OTLPSpanExporter` (gRPC to otel-collector:4317), auto-instrumentation for Flask, psycopg2, and requests (api-gateway + order-service)
- **Prometheus metrics**: `http_requests_total` Counter (labels: method, endpoint, code, service) and `http_request_duration_seconds` Histogram (labels: method, endpoint, service; buckets: 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
- **Health endpoints**: `/healthz` (liveness + readiness probes), `/metrics` (Prometheus scrape)
- **Runtime**: Gunicorn with 2 workers and 4 threads per worker

### Chaos Engineering

The payment-service exposes 4 fault injection endpoints and 2 control endpoints for reliability testing:

| Endpoint | Method | Effect |
|---|---|---|
| `/chaos/latency` | POST | Injects configurable `delay_ms` via `time.sleep()` on every request |
| `/chaos/errors` | POST | Returns HTTP 500 at configurable `error_rate` percentage |
| `/chaos/pg-flood` | POST | Opens `count` (default 80) idle PostgreSQL connections, exhausting `max_connections` |
| `/chaos/pg-slow` | POST | Runs `pg_sleep(3)` in background thread for `duration_sec` |
| `/chaos` | DELETE | Resets all chaos (closes flood connections, zeros all injection params) |
| `/chaos/status` | GET | Returns current chaos configuration |

Companion scripts in `scripts/chaos/` provide one-command fault injection: `deploy-broken.sh` (sets image to `busybox:latest` for CrashLoopBackOff), `inject-latency.sh`, `inject-errors.sh`, `pg-connection-flood.sh`, and `pg-slow-query.sh`. These scripts pair with the SRE runbooks — inject a fault, watch the alert fire, observe the MCP server's L1/L2 triage, and verify remediation.

---

## Scaling to Production

What changes when moving from this demo to enterprise scale:

| Component | Demo | Production |
|---|---|---|
| **Pulumi** | Single stack, local state | Micro-stacks (network/platform/data/app), Pulumi Cloud state, ESC for secrets, CrossGuard policies |
| **EKS** | 2x t3.medium, single cluster | Multi-AZ, Karpenter for autoscaling, Pod Identity, Istio/Cilium mesh, multi-cluster with ArgoCD |
| **VictoriaMetrics** | VMSingle (24h retention, 10Gi) | VMCluster (sharded vminsert/vmselect/vmstorage), object storage for long-term, vmauth for multi-tenancy |
| **OTel Collector** | Single gateway deployment | Agent DaemonSet + gateway fleet, tail-based sampling, per-signal backend routing |
| **Vector** | DaemonSet → console sink | DaemonSet → Aggregator tier → multi-sink (S3 archive, Elasticsearch search, Loki for Grafana) |
| **PostgreSQL** | Single db.t4g.micro, no backups | Multi-AZ, read replicas, RDS Proxy/PgBouncer, PITR backups, pg_stat_statements query reviews |
| **Grafana** | Single instance, anonymous auth | Grafana Cloud or HA deployment, Grafonnet dashboard-as-code, LDAP/SAML RBAC |
| **MCP Server** | Single pod, all 7 tools | Domain-specific servers, approval gates for destructive actions, audit logging, circuit breakers |
| **CI/CD** | Single workflow, non-blocking scan | Environment protection rules, matrix builds, canary deploys, blocking Trivy, DAST |
| **SRE** | 5 runbooks, manual postmortems | Automated runbook execution metrics, ML anomaly detection, error budget CI/CD gates |
