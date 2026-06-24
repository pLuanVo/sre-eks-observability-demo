"""ECR repositories component for all application container images."""

from dataclasses import dataclass, field
from typing import Optional, Sequence

import pulumi
from pulumi import Output, ResourceOptions
import pulumi_aws as aws


LIFECYCLE_POLICY = """{
    "rules": [{
        "rulePriority": 1,
        "description": "Keep last 10 images",
        "selection": {
            "tagStatus": "any",
            "countType": "imageCountMoreThan",
            "countNumber": 10
        },
        "action": {"type": "expire"}
    }]
}"""


@dataclass
class EcrReposArgs:
    service_names: Sequence[str] = (
        "api-gateway", "order-service", "payment-service", "mcp-server",
    )
    repo_prefix: str = "sre-demo"
    tags: dict = field(default_factory=dict)


class EcrRepos(pulumi.ComponentResource):
    repository_urls: dict[str, Output[str]]

    def __init__(
        self,
        name: str,
        args: EcrReposArgs,
        opts: Optional[ResourceOptions] = None,
    ) -> None:
        super().__init__("sre:infra:EcrRepos", name, {}, opts)

        child_opts = ResourceOptions(parent=self)
        self.repository_urls = {}

        for svc in args.service_names:
            repo = aws.ecr.Repository(
                f"{name}-{svc}",
                name=f"{args.repo_prefix}/{svc}",
                image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
                    scan_on_push=True,
                ),
                image_tag_mutability="MUTABLE",
                force_delete=True,
                tags=args.tags,
                opts=child_opts,
            )

            aws.ecr.LifecyclePolicy(
                f"{name}-{svc}-lifecycle",
                repository=repo.name,
                policy=LIFECYCLE_POLICY,
                opts=child_opts,
            )

            self.repository_urls[svc] = repo.repository_url

        self.register_outputs({
            f"ecr_{svc}": url for svc, url in self.repository_urls.items()
        })
