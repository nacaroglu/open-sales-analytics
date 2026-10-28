#!/usr/bin/env python3
"""Offline security assertions for the osa-observability CloudFormation stack."""
import re
import sys
from pathlib import Path


template = Path("deploy/cloudformation/osa-observability.yaml").read_text(encoding="utf-8")
readme = Path("deploy/README.md").read_text(encoding="utf-8").lower()


def require(condition: bool, message: str) -> None:
    if not condition:
        print(f"::error::{message}", file=sys.stderr)
        raise SystemExit(1)


resources = re.search(r"(?ms)^Resources:\n(?P<body>.*?)(?=^Outputs:)", template)
require(resources is not None, "observability Resources section is required")
body = resources.group("body") if resources else ""
names = re.findall(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):$", body)
require(set(names) == {
    "ObservabilitySecurityGroup", "ObservabilityInstanceProfile", "ObservabilityInstance",
    "TelemetryVolume", "TelemetryVolumeAttachment",
}, "observability stack must contain only its expected owned resources")
for export in (
    "osa-foundation-VpcId", "osa-foundation-PublicSubnetAz1Id",
    "osa-foundation-ObservabilityEc2InstanceRoleName",
):
    require(export in template, f"stack must import required export {export}")
require("osa-dev-AppSecurityGroupId" not in template and "osa-prod-AppSecurityGroupId" not in template,
        "observability stack must not import application-stack exports")

sg = re.search(r"(?ms)^  ObservabilitySecurityGroup:\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)", body)
require(sg is not None, "observability security group is required")
sg_body = sg.group("body") if sg else ""
require("FromPort: 80" in sg_body and "ToPort: 80" in sg_body
        and "FromPort: 443" in sg_body and "ToPort: 443" in sg_body,
        "public web ingress must allow only HTTP and HTTPS")
require(sg_body.count("CidrIp: 0.0.0.0/0") == 3,
        "only public HTTP/HTTPS ingress and HTTPS egress may use public IPv4")
require("FromPort: 22" not in body and "FromPort: 4317" not in sg_body
        and "FromPort: 4318" not in sg_body,
        "SSH and public OTLP ingress are prohibited")

require("HttpTokens: required" in body, "instance metadata v2 must be required")
profile = re.search(r"(?ms)^  ObservabilityInstanceProfile:\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)", body)
require(profile is not None and "osa-foundation-ObservabilityEc2InstanceRoleName" in profile.group("body"),
        "instance profile must import the dedicated least-privilege role")
require(re.search(r"(?m)^      Encrypted: true$", body) is not None
        and re.search(r"(?m)^            DeleteOnTermination: true$", body) is not None,
        "root and telemetry EBS volumes must be encrypted and ephemeral")
volume = re.search(r"(?ms)^  TelemetryVolume:\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)", body)
require(volume is not None and "DeletionPolicy: Delete" in volume.group("body")
        and "UpdateReplacePolicy: Delete" in volume.group("body")
        and "Encrypted: true" in volume.group("body"),
        "telemetry EBS must be encrypted and deleted on stack deletion or replacement")
require("Retain" not in body, "observability resources must not use Retain policies")

params = re.search(r"(?ms)^Parameters:\n(?P<body>.*?)(?=^Resources:)", template)
require(params is not None, "constrained deployment parameters are required")
for phrase in ("AllowedPattern:", "ConstraintDescription:", "MinLength:", "MaxLength:"):
    require(phrase in params.group("body"), f"deployment parameters must include {phrase}")
require("/osa/observability/grafana/admin-password" in template
        and "Password:" not in template and "SecretAccessKey" not in template
        and "resolve:ssm-secure" not in template,
        "template may reference the fixed secret parameter name but contain no secret value")
userdata = re.search(r"(?ms)^      UserData:\n(?P<body>.*?)(?=^      Tags:)", body)
require(userdata is not None and "GrafanaParameter: !Ref GrafanaAdminParameterName" in userdata.group("body")
        and "admin-password" not in userdata.group("body").lower(),
        "user data must pass only a parameter reference, never credentials")

outputs = re.search(r"(?ms)^Outputs:\n(?P<body>.*)\Z", template)
output_body = outputs.group("body") if outputs else ""
output_names = re.findall(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):$", output_body)
require(set(output_names) == {
    "GrafanaPublicIp", "GrafanaUrl", "CollectorPrivateEndpoint", "CollectorSecurityGroupId",
},
        "only nonsecret connection outputs may be exposed")
require("https://${GrafanaHostname}" in template and "http://${ObservabilityInstance.PrivateIp}:4318" in template,
        "outputs must provide HTTPS Grafana and private OTLP endpoints")
collector_endpoint = re.search(
    r"(?ms)^  CollectorPrivateEndpoint:\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)",
    output_body,
)
require(
    collector_endpoint is not None
    and "Value: !Sub \"http://${ObservabilityInstance.PrivateIp}:4318\"" in collector_endpoint.group("body")
    and "Name: !Sub '${AWS::StackName}-CollectorPrivateEndpoint'" in collector_endpoint.group("body"),
    "the private Collector endpoint must be exported for application stacks",
)
collector_sg = re.search(
    r"(?ms)^  CollectorSecurityGroupId:\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)",
    output_body,
)
require(
    collector_sg is not None
    and "Value: !GetAtt ObservabilitySecurityGroup.GroupId" in collector_sg.group("body")
    and 'Name: !Sub "${AWS::StackName}-CollectorSecurityGroupId"' in collector_sg.group("body"),
    "the private Collector security group ID must be exported for the application stacks",
)
require("observabilityexecutionrole" in readme and "observabilityec2instancerole" in readme
        and "securestring" in readme and "/osa/observability/grafana/admin-password" in readme,
        "deployment docs must describe the two IAM roles and SecureString prerequisite")
require("osa-dev-appsecuritygroupid" not in readme and "osa-prod-appsecuritygroupid" not in readme,
        "deployment docs must not describe application security-group imports into observability")
require("collectorsecuritygroupid" in readme and "collectorprivateendpoint" in readme
        and "osa-dev" in readme and "osa-prod" in readme,
        "deployment docs must describe the exported Collector security group and endpoint used by app stacks")
print("osa-observability CloudFormation security invariants passed")
