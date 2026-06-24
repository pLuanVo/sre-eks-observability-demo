"""RDS PostgreSQL 17 component with observability-tuned parameter group."""

from dataclasses import dataclass, field
from typing import Optional

import pulumi
from pulumi import Input, Output, ResourceOptions
import pulumi_aws as aws


@dataclass
class RdsDatabaseArgs:
    vpc_id: Input[str] = ""
    subnet_ids: Input[list[str]] = field(default_factory=list)
    allowed_security_group_id: Input[str] = ""
    instance_class: str = "db.t4g.micro"
    db_name: str = "sre_demo"
    username: str = "sreadmin"
    password: Input[str] = ""
    tags: dict = field(default_factory=dict)


class RdsDatabase(pulumi.ComponentResource):
    endpoint: Output[str]
    port: Output[str]
    db_name: Output[str]

    def __init__(
        self,
        name: str,
        args: RdsDatabaseArgs,
        opts: Optional[ResourceOptions] = None,
    ) -> None:
        super().__init__("sre:infra:RdsDatabase", name, {}, opts)

        child_opts = ResourceOptions(parent=self)

        param_group = aws.rds.ParameterGroup(
            f"{name}-pg17",
            family="postgres17",
            description="PostgreSQL 17 tuned for SRE observability demo",
            parameters=[
                aws.rds.ParameterGroupParameterArgs(
                    name="shared_preload_libraries",
                    value="pg_stat_statements",
                    apply_method="pending-reboot",
                ),
                aws.rds.ParameterGroupParameterArgs(
                    name="pg_stat_statements.track",
                    value="all",
                    apply_method="pending-reboot",
                ),
                aws.rds.ParameterGroupParameterArgs(
                    name="log_min_duration_statement",
                    value="100",
                    apply_method="pending-reboot",
                ),
                aws.rds.ParameterGroupParameterArgs(
                    name="max_connections",
                    value="100",
                    apply_method="pending-reboot",
                ),
                aws.rds.ParameterGroupParameterArgs(
                    name="log_statement",
                    value="ddl",
                    apply_method="pending-reboot",
                ),
            ],
            tags=args.tags,
            opts=child_opts,
        )

        subnet_group = aws.rds.SubnetGroup(
            f"{name}-subnets",
            subnet_ids=args.subnet_ids,
            tags=args.tags,
            opts=child_opts,
        )

        security_group = aws.ec2.SecurityGroup(
            f"{name}-sg",
            vpc_id=args.vpc_id,
            description="Allow PostgreSQL from EKS nodes",
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    protocol="tcp",
                    from_port=5432,
                    to_port=5432,
                    security_groups=[args.allowed_security_group_id],
                ),
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=["0.0.0.0/0"],
                ),
            ],
            tags=args.tags,
            opts=child_opts,
        )

        instance = aws.rds.Instance(
            f"{name}-instance",
            engine="postgres",
            engine_version="17",
            instance_class=args.instance_class,
            allocated_storage=20,
            db_name=args.db_name,
            username=args.username,
            password=args.password,
            parameter_group_name=param_group.name,
            db_subnet_group_name=subnet_group.name,
            vpc_security_group_ids=[security_group.id],
            publicly_accessible=False,
            skip_final_snapshot=True,
            multi_az=False,
            storage_type="gp3",
            backup_retention_period=0,
            tags=args.tags,
            opts=child_opts,
        )

        self.endpoint = instance.address
        self.port = instance.port.apply(lambda p: str(p))
        self.db_name = pulumi.Output.from_input(args.db_name)

        self.register_outputs({
            "endpoint": self.endpoint,
            "port": self.port,
            "db_name": self.db_name,
        })
