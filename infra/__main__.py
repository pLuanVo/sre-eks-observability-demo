"""SRE EKS Observability Platform — Pulumi IaC entrypoint.

Provisions: VPC, EKS cluster, RDS PostgreSQL 17, ECR repos, IAM OIDC.
Uses ComponentResource pattern for reusable, composable infrastructure.
"""

import pulumi

from config import settings
from components import (
    Vpc, VpcArgs,
    EksCluster, EksClusterArgs,
    RdsDatabase, RdsDatabaseArgs,
    EcrRepos, EcrReposArgs,
    IamGithubOidc, IamGithubOidcArgs,
)

# --- Network ---
vpc = Vpc("main", VpcArgs(
    cidr_block="10.0.0.0/16",
    number_of_azs=2,
    tags=settings.base_tags,
))

# --- Compute ---
cluster = EksCluster("app", EksClusterArgs(
    vpc_id=vpc.vpc_id,
    private_subnet_ids=vpc.private_subnet_ids,
    public_subnet_ids=vpc.public_subnet_ids,
    instance_type=settings.node_instance_type,
    node_count=settings.node_count,
    tags=settings.base_tags,
))

# --- Data ---
database = RdsDatabase("demo", RdsDatabaseArgs(
    vpc_id=vpc.vpc_id,
    subnet_ids=vpc.private_subnet_ids,
    allowed_security_group_id=cluster.node_security_group_id,
    instance_class=settings.db_instance_class,
    db_name=settings.db_name,
    username=settings.db_username,
    password=settings.db_password,
    tags=settings.base_tags,
))

# --- Container Registry ---
ecr = EcrRepos("images", EcrReposArgs(
    tags=settings.base_tags,
))

# --- CI/CD ---
iam = IamGithubOidc("ci", IamGithubOidcArgs(
    github_repo=settings.github_repo,
    eks_cluster_name=cluster.cluster_name,
    tags=settings.base_tags,
))

# --- Stack Outputs ---
pulumi.export("kubeconfig", cluster.kubeconfig)
pulumi.export("cluster_name", cluster.cluster_name)
pulumi.export("region", settings.region)
pulumi.export("vpc_id", vpc.vpc_id)

pulumi.export("db_endpoint", database.endpoint)
pulumi.export("db_port", database.port)
pulumi.export("db_name", database.db_name)
pulumi.export("db_password", pulumi.Output.secret(settings.db_password))

for svc_name, url in ecr.repository_urls.items():
    pulumi.export(f"ecr_{svc_name}", url)

pulumi.export("github_actions_role_arn", iam.role_arn)
