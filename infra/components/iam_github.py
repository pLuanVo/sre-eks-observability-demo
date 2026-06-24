"""IAM component: GitHub Actions OIDC federation + EKS access entry for CI/CD."""

import json
from dataclasses import dataclass, field
from typing import Optional

import pulumi
from pulumi import Input, Output, ResourceOptions
import pulumi_aws as aws


@dataclass
class IamGithubOidcArgs:
    github_repo: str = "pLuanVo/sre-eks-observability-demo"
    eks_cluster_name: Input[str] = ""
    tags: dict = field(default_factory=dict)


class IamGithubOidc(pulumi.ComponentResource):
    role_arn: Output[str]

    def __init__(
        self,
        name: str,
        args: IamGithubOidcArgs,
        opts: Optional[ResourceOptions] = None,
    ) -> None:
        super().__init__("sre:infra:IamGithubOidc", name, {}, opts)

        child_opts = ResourceOptions(parent=self)

        oidc_provider = aws.iam.OpenIdConnectProvider(
            f"{name}-oidc",
            url="https://token.actions.githubusercontent.com",
            client_id_lists=["sts.amazonaws.com"],
            thumbprint_lists=["ffffffffffffffffffffffffffffffffffffffff"],
            tags=args.tags,
            opts=child_opts,
        )

        role = aws.iam.Role(
            f"{name}-role",
            assume_role_policy=oidc_provider.arn.apply(
                lambda arn: json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {"Federated": arn},
                        "Action": "sts:AssumeRoleWithWebIdentity",
                        "Condition": {
                            "StringEquals": {
                                "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                            },
                            "StringLike": {
                                "token.actions.githubusercontent.com:sub": f"repo:{args.github_repo}:*",
                            },
                        },
                    }],
                })
            ),
            tags=args.tags,
            opts=child_opts,
        )

        for policy_name, policy_arn in [
            ("ecr-push", "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"),
            ("eks-access", "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"),
        ]:
            aws.iam.RolePolicyAttachment(
                f"{name}-{policy_name}",
                role=role.name,
                policy_arn=policy_arn,
                opts=child_opts,
            )

        aws.iam.RolePolicy(
            f"{name}-eks-describe",
            role=role.name,
            policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Action": [
                        "eks:DescribeCluster",
                        "eks:ListClusters",
                    ],
                    "Resource": "*",
                }],
            }),
            opts=child_opts,
        )

        # EKS access entry — allows CI role to interact with the K8s API
        access_entry = aws.eks.AccessEntry(
            f"{name}-eks-access",
            cluster_name=args.eks_cluster_name,
            principal_arn=role.arn,
            type="STANDARD",
            tags=args.tags,
            opts=child_opts,
        )

        aws.eks.AccessPolicyAssociation(
            f"{name}-eks-admin",
            cluster_name=args.eks_cluster_name,
            principal_arn=role.arn,
            policy_arn="arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy",
            access_scope=aws.eks.AccessPolicyAssociationAccessScopeArgs(
                type="cluster",
            ),
            opts=ResourceOptions(parent=self, depends_on=[access_entry]),
        )

        self.role_arn = role.arn

        self.register_outputs({
            "role_arn": self.role_arn,
        })
