"""EKS cluster component with managed node group and OIDC provider."""

from dataclasses import dataclass, field
from typing import Optional, Sequence

import pulumi
from pulumi import Input, Output, ResourceOptions
import pulumi_eks as eks


@dataclass
class EksClusterArgs:
    vpc_id: Input[str] = ""
    private_subnet_ids: Input[Sequence[str]] = field(default_factory=list)
    public_subnet_ids: Input[Sequence[str]] = field(default_factory=list)
    instance_type: str = "t3.medium"
    node_count: int = 2
    tags: dict = field(default_factory=dict)


class EksCluster(pulumi.ComponentResource):
    cluster_name: Output[str]
    kubeconfig: Output[dict]
    node_security_group_id: Output[str]
    oidc_provider_url: Output[str]
    oidc_provider_arn: Output[str]

    def __init__(
        self,
        name: str,
        args: EksClusterArgs,
        opts: Optional[ResourceOptions] = None,
    ) -> None:
        super().__init__("sre:infra:EksCluster", name, {}, opts)

        self._cluster = eks.Cluster(
            f"{name}-cluster",
            vpc_id=args.vpc_id,
            private_subnet_ids=args.private_subnet_ids,
            public_subnet_ids=args.public_subnet_ids,
            instance_type=args.instance_type,
            desired_capacity=args.node_count,
            min_size=args.node_count,
            max_size=args.node_count + 1,
            node_associate_public_ip_address=False,
            create_oidc_provider=True,
            authentication_mode=eks.AuthenticationMode.API_AND_CONFIG_MAP,
            tags=args.tags,
            opts=ResourceOptions(parent=self),
        )

        self.cluster_name = self._cluster.eks_cluster.name
        self.kubeconfig = self._cluster.kubeconfig
        self.node_security_group_id = self._cluster.node_security_group.id
        self.oidc_provider_url = self._cluster.core.oidc_provider.url
        self.oidc_provider_arn = self._cluster.core.oidc_provider.arn

        self.register_outputs({
            "cluster_name": self.cluster_name,
            "kubeconfig": self.kubeconfig,
            "node_security_group_id": self.node_security_group_id,
        })
