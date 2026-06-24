"""Centralized configuration loader for all infrastructure components."""

import pulumi


_config = pulumi.Config()
_aws_config = pulumi.Config("aws")


class AppConfig:
    environment: str = pulumi.get_stack()
    region: str = _aws_config.require("region")

    cluster_name: str = _config.get("cluster-name") or "sre-demo"
    node_instance_type: str = _config.get("node-instance-type") or "t3.medium"
    node_count: int = _config.get_int("node-count") or 2

    db_instance_class: str = _config.get("db-instance-class") or "db.t4g.micro"
    db_name: str = _config.get("db-name") or "sre_demo"
    db_username: str = _config.get("db-username") or "sreadmin"
    db_password: pulumi.Output[str] = _config.require_secret("db-password")

    github_repo: str = _config.get("github-repo") or "pLuanVo/sre-eks-observability-demo"

    project_tag: str = "sre-eks-observability"

    @property
    def base_tags(self) -> dict:
        return {
            "Project": self.project_tag,
            "Environment": self.environment,
            "ManagedBy": "pulumi",
        }


settings = AppConfig()
