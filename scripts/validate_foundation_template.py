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

role_match = re.search(r"(?ms)^  FoundationExecutionRole:\n(?P<body>.*?)(?=^Outputs:)", text)
require(role_match is not None, "foundation execution role policy is required")
role_statements = re.findall(
    r"(?ms)^\s+- Sid: ([A-Za-z0-9]+)\n(?P<body>.*?)(?=^\s+- Sid:|\Z)",
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
resources_match = re.search(r"(?ms)^Resources:\n(?P<body>.*?)(?=^Outputs:)", text)
require(resources_match is not None, "CloudFormation Resources section is required")
resource_blocks = re.findall(
    r"(?ms)^  ([A-Za-z][A-Za-z0-9]*):\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)",
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
README = Path("deploy/README.md")
readme = README.read_text(encoding="utf-8")


def foundation_resources(source: str) -> dict[str, tuple[str, str]]:
    section = re.search(r"(?ms)^Resources:\n(?P<body>.*?)(?=^Outputs:|\Z)", source)
    require(section is not None, "CloudFormation Resources section is missing")
    starts = list(re.finditer(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):\n", section.group("body")))
    resources: dict[str, tuple[str, str]] = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(section.group("body"))
        body = section.group("body")[match.end():end]
        type_match = re.search(r"(?m)^    Type: ([^\n]+)$", body)
        require(type_match is not None, f"{match.group(1)} is missing a CloudFormation Type")
        resources[match.group(1)] = (type_match.group(1), body)
    return resources


resources = foundation_resources(text)
expected_subnets = {
    "PublicSubnetAz1",
    "PublicSubnetAz2",
    "PrivateSubnetAz1",
    "PrivateSubnetAz2",
}
for name in sorted(expected_subnets):
    require(name in resources, f"required foundation subnet {name} is missing")
    resource_type, body = resources[name]
    require(resource_type == "AWS::EC2::Subnet", f"{name} must remain an EC2 subnet")
    require(
        re.search(r"(?m)^      MapPublicIpOnLaunch: false$", body) is not None,
        f"{name} must keep MapPublicIpOnLaunch set to false",
    )

expected_associations = {
    "PublicRouteAssociationAz1": ("PublicRouteTable", "PublicSubnetAz1"),
    "PublicRouteAssociationAz2": ("PublicRouteTable", "PublicSubnetAz2"),
    "PrivateRouteAssociationAz1": ("PrivateRouteTableAz1", "PrivateSubnetAz1"),
    "PrivateRouteAssociationAz2": ("PrivateRouteTableAz2", "PrivateSubnetAz2"),
}
associations: dict[str, tuple[str, str]] = {}
for name, (resource_type, body) in resources.items():
    if resource_type != "AWS::EC2::SubnetRouteTableAssociation":
        continue
    route_table = re.search(r"(?m)^      RouteTableId: !Ref (\w+)$", body)
    subnet = re.search(r"(?m)^      SubnetId: !Ref (\w+)$", body)
    require(
        route_table is not None and subnet is not None,
        f"{name} must explicitly identify its route table and subnet",
    )
    associations[name] = (route_table.group(1), subnet.group(1))
require(
    associations == expected_associations,
    "route-table associations must be exactly the two public subnets on PublicRouteTable and each private subnet on its own table",
)

route_resources = {
    name: body
    for name, (resource_type, body) in resources.items()
    if resource_type == "AWS::EC2::Route"
}
require(
    set(route_resources) == {"PublicDefaultRoute"},
    "foundation must contain only its declared public default route; do not add private or unreviewed egress routes",
)
public_route = route_resources["PublicDefaultRoute"]
require(
    re.search(r"(?m)^      RouteTableId: !Ref PublicRouteTable$", public_route) is not None
    and re.search(r"(?m)^      DestinationCidrBlock: 0\.0\.0\.0/0$", public_route) is not None
    and re.search(r"(?m)^      GatewayId: !Ref InternetGateway$", public_route) is not None,
    "PublicDefaultRoute must send 0.0.0.0/0 through InternetGateway on PublicRouteTable",
)

for name, (resource_type, body) in resources.items():
    require(
        resource_type not in {
            "AWS::EC2::SecurityGroup",
            "AWS::EC2::SecurityGroupIngress",
            "AWS::EC2::SecurityGroupEgress",
            "AWS::EC2::NetworkAcl",
            "AWS::EC2::NetworkAclEntry",
            "AWS::EC2::SubnetNetworkAclAssociation",
        },
        f"{name} must not add security-group or network-ACL resources to the foundation",
    )
    require(
        not resource_type.endswith("::Listener")
        and not resource_type.startswith(
            ("AWS::ElasticLoadBalancing", "AWS::ApiGateway", "AWS::GlobalAccelerator")
        ),
        f"{name} must not introduce a public listener in the foundation",
    )
    require(
        not resource_type.startswith(
            (
                "AWS::EC2::NatGateway",
                "AWS::EC2::VPCPeeringConnection",
                "AWS::EC2::TransitGateway",
                "AWS::EC2::EgressOnlyInternetGateway",
            )
        ),
        f"{name} must not introduce an unreviewed private egress path",
    )

doc = readme.lower()
for phrase, message in (
    ("public ssh", "README must explicitly deny public SSH"),
    ("tcp 22", "README must document public SSH port 22 as prohibited"),
    ("public otlp", "README must explicitly deny public OTLP"),
    ("tcp 4317", "README must document public OTLP port 4317 as prohibited"),
    ("tcp 4318", "README must document public OTLP port 4318 as prohibited"),
    ("owning workload stack", "README must assign workload egress to its owning stack"),
    ("limited to that purpose", "README must require purpose-limited workload egress"),
    ("issue #240", "README must assign app ingress to issue #240"),
    ("issue #263", "README must assign Grafana ingress to issue #263"),
    ("issue #264", "README must assign Collector OTLP access to issue #264"),
    (
        "no stack, vpc, route, security group, local generated file, or credential",
        "README must define the no-resource cleanup boundary",
    ),
    ("creates no aws resources", "README must state CI validation creates no AWS resources"),
):
    require(phrase in doc, message)
for reference in ("#240", "#263", "#264"):
    require(reference in readme, f"README must identify workload ownership {reference}")
for url in (
    "https://docs.aws.amazon.com/vpc/latest/userguide/subnet-route-tables.html",
    "https://docs.aws.amazon.com/us_en/AWSEC2/latest/UserGuide/working-with-ip-addresses.html",
    "https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html",
):
    require(url in readme, f"README must cite the applicable AWS source: {url}")

print("Foundation static security and network-boundary assertions passed.")
