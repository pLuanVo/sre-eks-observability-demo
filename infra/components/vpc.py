"""VPC component with public/private subnets across 2 AZs and a single NAT Gateway."""

from dataclasses import dataclass, field
from typing import Optional

import pulumi
from pulumi import Input, Output, ResourceOptions
import pulumi_awsx as awsx


@dataclass
class VpcArgs:
    cidr_block: Input[str] = "10.0.0.0/16"
    number_of_azs: int = 2
    tags: dict = field(default_factory=dict)


class Vpc(pulumi.ComponentResource):
    vpc_id: Output[str]
    private_subnet_ids: Output[list[str]]
    public_subnet_ids: Output[list[str]]

    def __init__(
        self,
        name: str,
        args: VpcArgs,
        opts: Optional[ResourceOptions] = None,
    ) -> None:
        super().__init__("sre:infra:Vpc", name, {}, opts)

        self._vpc = awsx.ec2.Vpc(
            f"{name}-vpc",
            cidr_block=args.cidr_block,
            number_of_availability_zones=args.number_of_azs,
            nat_gateways=awsx.ec2.NatGatewayConfigurationArgs(
                strategy=awsx.ec2.NatGatewayStrategy.SINGLE,
            ),
            subnet_specs=[
                awsx.ec2.SubnetSpecArgs(type=awsx.ec2.SubnetType.PUBLIC, cidr_mask=24),
                awsx.ec2.SubnetSpecArgs(type=awsx.ec2.SubnetType.PRIVATE, cidr_mask=24),
            ],
            tags=args.tags,
            opts=ResourceOptions(parent=self),
        )

        self.vpc_id = self._vpc.vpc_id
        self.private_subnet_ids = self._vpc.private_subnet_ids
        self.public_subnet_ids = self._vpc.public_subnet_ids

        self.register_outputs({
            "vpc_id": self.vpc_id,
            "private_subnet_ids": self.private_subnet_ids,
            "public_subnet_ids": self.public_subnet_ids,
        })
