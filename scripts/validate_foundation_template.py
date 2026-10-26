#!/usr/bin/env python3
"""Static security assertions for the offline-validated OSA foundation template."""
from pathlib import Path
import re
import sys

TEMPLATE = Path("deploy/cloudformation/osa-foundation.yaml")
text = TEMPLATE.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        print(f"::error::{message}", file=sys.stderr)
        raise SystemExit(1)


require("EnableDnsSupport: true" in text and "EnableDnsHostnames: true" in text, "VPC DNS must be enabled")
for name in ("PublicSubnetAz1", "PublicSubnetAz2", "PrivateSubnetAz1", "PrivateSubnetAz2"):
    require(re.search(rf"^  {name}:\n    Type: AWS::EC2::Subnet$", text, re.MULTILINE) is not None,
            f"missing subnet resource {name}")
require("AvailabilityZonesMustDiffer:" in text, "AZ inequality must be asserted")
require("DestinationCidrBlock: 0.0.0.0/0\n      GatewayId: !Ref InternetGateway" in text,
        "public default route must use the attached internet gateway")
require("PrivateRouteTableAz1:" in text and "PrivateRouteTableAz2:" in text, "private route tables required")
require("Type: AWS::EC2::SecurityGroup" not in text and "AWS::EC2::SecurityGroupIngress" not in text,
        "foundation template must not create security groups or ingress rules")
require("ImageTagMutability: IMMUTABLE" in text and "ScanOnPush: true" in text,
        "ECR must use immutable tags and scan on push")
require("LifecyclePolicy" not in text and "EmptyOnDelete" not in text,
        "ECR lifecycle and empty-on-delete belong to issue #236")
require("Url: https://token.actions.githubusercontent.com" in text and "- sts.amazonaws.com" in text,
        "GitHub OIDC provider URL and audience must be exact")
require("token.actions.githubusercontent.com:sub: !Sub \"repo:${GitHubOwner}/${GitHubRepository}:ref:refs/heads/${GitHubMainBranch}\"" in text,
        "OIDC subject must be exact owner/repository/branch without wildcard")
require("Resource: !GetAtt Repository.Arn" in text, "build/push ECR actions must be repository scoped")
require("FoundationExecutionRole:" in text and "BuildRole:" in text, "separate baseline roles are required")

role_match = re.search(r"(?ms)^  FoundationExecutionRole:\\n(?P<body>.*?)(?=^Outputs:)", text)
require(role_match is not None, "foundation execution role policy is required")
role_statements = re.findall(
    r"(?ms)^\\s+- Sid: ([A-Za-z0-9]+)\\n(?P<body>.*?)(?=^\\s+- Sid:|\\Z)",
    role_match.group("body"),
)
create_route_table = next(
    (body for sid, body in role_statements if sid == "CreateRouteTableInVpc"),
    "",
)
require(
    "ec2:CreateRouteTable" in create_route_table
    and "route-table/*" in create_route_table
    and "vpc/*" in create_route_table,
    "ec2:CreateRouteTable must be scoped to both route-table and VPC resources",
)
resources_match = re.search(r"(?ms)^Resources:\\n(?P<body>.*?)(?=^Outputs:)", text)
require(resources_match is not None, "CloudFormation Resources section is required")
resource_blocks = re.findall(
    r"(?ms)^  ([A-Za-z][A-Za-z0-9]*):\\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\\n|\\Z)",
    resources_match.group("body"),
)
for resource_name, resource_body in resource_blocks:
    if "Type: AWS::EC2::Route" in resource_body:
        require(
            "PrivateRouteTableAz1" not in resource_body
            and "PrivateRouteTableAz2" not in resource_body,
            f"{resource_name} must not target a private route table",
        )
require("${AWS::StackName}-VpcId" in text and "${AWS::StackName}-PrivateSubnetIds" in text
        and "${AWS::StackName}-PublicSubnetIds" in text and "${AWS::StackName}-RepositoryUri" in text,
        "shared outputs must have stack-qualified exports")
require("Password:" not in text and "SecretAccessKey" not in text
        and re.search(r"(?<!\d)\d{12}(?!\d)", text) is None,
        "template must not include credentials or hardcoded account IDs")
print("Foundation static security assertions passed.")
