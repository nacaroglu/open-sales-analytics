#!/usr/bin/env python3
"""Offline assertions for the parameterized OSA application release contract."""
import re
import sys
import textwrap
from pathlib import Path

TEMPLATE = Path("deploy/cloudformation/osa-application.yaml")
text = TEMPLATE.read_text(encoding="utf-8")

def require(condition: bool, message: str) -> None:
    if not condition:
        print(f"::error::{message}", file=sys.stderr)
        raise SystemExit(1)


# CloudFormation's generated Caddyfile must stay identical to the runtime template,
# including the narrow, exact Bearer API bypass matcher.
caddy_template = Path("Caddyfile.deploy").read_text(encoding="utf-8").strip()
caddy_match = re.search(r"(?ms)^\s+cat > /opt/osa/Caddyfile <<'CADDY'\n(?P<body>.*?)^\s+CADDY$", text)
require(caddy_match is not None, "CloudFormation must generate the deployment Caddyfile")
embedded_caddy = textwrap.dedent(caddy_match.group("body")).strip()
embedded_caddy = embedded_caddy[embedded_caddy.rindex("{$PUBLIC_HOSTNAME} {"):]
embedded_caddy = embedded_caddy.replace("{$PUBLIC_HOSTNAME}", "{$OSA_HOSTNAME}")
def normalized(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]
require(normalized(embedded_caddy) == normalized(caddy_template), "CloudFormation and tracked deployment Caddyfiles must match")
require(
    "path_regexp dataset_api ^/api/datasets/[A-Za-z0-9_-]{22}(/.*)?$" in caddy_template
    and "header_regexp bearer Authorization ^Bearer[[:blank:]]+[A-Za-z0-9_-]{43}$" in caddy_template
    and caddy_template.index("handle @dataset_api {") < caddy_template.index("\n\thandle {"),
    "Caddy Basic Auth bypass must require an exact dataset-ID path and Bearer-shaped Authorization header",
)



application_templates = sorted(Path("deploy/cloudformation").glob("osa-application*.yaml"))
require(application_templates == [TEMPLATE],
        "exactly one shared osa-application.yaml template must exist; do not add environment copies")

environment_match = re.search(r"(?ms)^  Environment:\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)", text)
require(environment_match is not None, "Environment parameter is required")
environment = environment_match.group("body")
require(re.findall(r"(?m)^      - (.+)$", environment) == ["development", "production"],
        "Environment must be restricted to development and production")

digest_match = re.search(r"(?ms)^  ImageDigest:\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)", text)
require(digest_match is not None, "explicit ImageDigest parameter is required")
digest = digest_match.group("body")
require('AllowedPattern: "^[a-f0-9]{64}$"' in digest and "MinLength: 64" in digest and "MaxLength: 64" in digest,
        "ImageDigest must accept exactly 64 lowercase hexadecimal digest characters, not a mutable tag/reference")

version_match = re.search(r"(?ms)^  ReleaseVersion:\n(?P<body>.*?)(?=^Conditions:|^Resources:|\Z)", text)
require(version_match is not None, "explicit ReleaseVersion parameter is required")
version = version_match.group("body")
require("MinLength: 1" in version and 'AllowedPattern: "^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$"' in version,
        "ReleaseVersion must be non-empty and readable")

ami_match = re.search(r"(?ms)^  AmiId:\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)", text)
require(ami_match is not None, "explicit AmiId parameter is required")
ami = ami_match.group("body")
require("Type: AWS::EC2::Image::Id" in ami
        and 'AllowedPattern: "^ami-[a-f0-9]{8,17}$"' in ami
        and "MinLength: 12" in ami and "MaxLength: 21" in ami,
        "AmiId must validate the lowercase AMI identifier format")

instance_type_match = re.search(r"(?ms)^  InstanceType:\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)", text)
require(instance_type_match is not None, "explicit InstanceType parameter is required")
instance_type = instance_type_match.group("body")
require('AllowedPattern: "^[a-z][0-9][a-z0-9]*\\\\.[a-z0-9]+$"' in instance_type,
        "InstanceType must validate an EC2 instance type format")

hostname_match = re.search(r"(?ms)^  PublicHostname:\n(?P<body>.*?)(?=^Conditions:|^Resources:|\Z)", text)
require(hostname_match is not None, "explicit PublicHostname parameter is required")
hostname = hostname_match.group("body")
require(
    'AllowedPattern: "^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\\\\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"' in hostname
    and "MinLength: 3" in hostname and "MaxLength: 253" in hostname,
    "PublicHostname must validate a dotted hostname with bounded DNS labels",
)

parameters = re.search(r"(?ms)^Parameters:\n(?P<body>.*?)(?=^Conditions:|^Resources:|\Z)", text)
require(parameters is not None, "Parameters section is required")
parameter_names = re.findall(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):\n", parameters.group("body"))
require(
    set(parameter_names) == {"Environment", "ImageDigest", "ReleaseVersion", "AmiId", "InstanceType", "PublicHostname"}
    and len(parameter_names) == 6,
    "the exact parameter set must include release metadata and the three explicit runtime parameters",
)

resources = re.search(r"(?ms)^Resources:\n(?P<body>.*?)(?=^Outputs:|\Z)", text)
require(resources is not None, "Resources section is required")
resource_body = resources.group("body")
resource_names = re.findall(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):\n    Type:", resource_body)
expected_resources = [
    "ReleaseImageMetadataParameter",
    "OsaInstanceProfile",
    "AppSecurityGroup",
    "AppInstance",
    "AppElasticIp",
    "AppElasticIpAssociation",
]
require(resource_names == expected_resources,
        "application resources must be exactly the release parameter, one instance profile/instance, one security group, and one Elastic IP association")
resource_blocks = {
    name: match.group("body")
    for name in resource_names
    for match in [re.search(rf"(?ms)^  {name}:\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)", resource_body)]
    if match is not None
}
require(set(resource_blocks) == set(expected_resources), "every approved application resource must have one complete resource block")
release_resource_body = resource_blocks["ReleaseImageMetadataParameter"]
require(
    "    Type: AWS::SSM::Parameter" in release_resource_body
    and re.findall(r"(?m)^      Type: (.+)$", release_resource_body) == ["String"]
    and "SecureString" not in release_resource_body,
    "release metadata must be exactly one non-secret SSM String parameter",
)
require("Name: !If\n        - IsDevelopment\n        - /osa/dev/release/image\n        - /osa/prod/release/image" in release_resource_body,
        "parameter path must map development to /osa/dev and production to /osa/prod")
require("Fn::ImportValue: osa-foundation-RepositoryUri" in release_resource_body
        and '"${RepositoryUri}@sha256:${Digest}"' in resource_body
        and "Digest: !Ref ImageDigest" in resource_body,
        "parameter value must import the foundation repository URI and append the validated digest")
require("Project: open-sales-analytics" in release_resource_body and "Environment: !Ref Environment" in release_resource_body
        and "OSAStack: !If [IsDevelopment, osa-dev, osa-prod]" in release_resource_body,
        "the metadata parameter must carry project and environment-derived stack identity tags")
profile = resource_blocks["OsaInstanceProfile"]
profile_roles = re.search(r"(?ms)^      Roles:\n(?P<body>.*?)(?=^      Tags:|\Z)", profile)
require(profile_roles is not None
        and "- !If" in profile_roles.group("body")
        and "IsDevelopment" in profile_roles.group("body")
        and "Fn::ImportValue: osa-foundation-DevCaddyAuthEc2InstanceRoleName" in profile_roles.group("body")
        and '"${FoundationStackName}-ec2-instance"' in profile_roles.group("body")
        and profile_roles.group("body").count("Fn::ImportValue: osa-foundation-StackName") == 1
        and "InstanceProfileName: !Sub \"${AWS::StackName}-instance-profile\"" in profile
        and "Path: !Sub \"/${AWS::StackName}/\"" in profile
        and "AWS::IAM::Role" not in resource_body,
        "the app-owned profile must select the dev-only auth role or production baseline role and use its own stack path/name")
require("Fn::ImportValue: osa-foundation-VpcId" in resource_blocks["AppSecurityGroup"]
        and "Fn::ImportValue: osa-foundation-PublicSubnetAz1Id" in resource_blocks["AppInstance"],
        "application networking must import the foundation VPC and first public subnet")
require("Fn::ImportValue: osa-foundation-RepositoryUri" in resource_blocks["AppInstance"]
        and "Fn::ImportValue: osa-foundation-StackName" in resource_blocks["OsaInstanceProfile"],
        "runtime must import the repository URI and foundation role-name contract")
imports = re.findall(r"Fn::ImportValue: (osa-foundation-[A-Za-z0-9]+)", text)
require(sorted(imports) == sorted([
    "osa-foundation-RepositoryUri", "osa-foundation-RepositoryUri", "osa-foundation-RepositoryUri",
    "osa-foundation-StackName", "osa-foundation-DevCaddyAuthEc2InstanceRoleName",
    "osa-foundation-VpcId", "osa-foundation-PublicSubnetAz1Id",
]), "template must use only the documented foundation repository, stack name, VPC, and public subnet exports")

security_group = resource_blocks["AppSecurityGroup"]
require("AWS::EC2::SecurityGroup" in security_group, "AppSecurityGroup must be an EC2 security group")
ingress = re.search(r"(?ms)^      SecurityGroupIngress:\n(?P<body>.*?)(?=^      SecurityGroupEgress:|\Z)", security_group)
egress = re.search(r"(?ms)^      SecurityGroupEgress:\n(?P<body>.*?)(?=^      Tags:|\Z)", security_group)
require(ingress is not None and egress is not None, "security group must declare explicit ingress and egress rules")
ingress_rules = re.findall(r"(?ms)^        - Description:.*?(?=^        - Description:|\Z)", ingress.group("body"))
require(len(ingress_rules) == 2, "security group must declare exactly HTTP and HTTPS ingress")
require(re.findall(r"(?m)^          IpProtocol: (.+)$", ingress.group("body")) == ["tcp", "tcp"]
        and re.findall(r"(?m)^          CidrIp: (.+)$", ingress.group("body")) == ["0.0.0.0/0", "0.0.0.0/0"]
        and "CidrIpv6:" not in ingress.group("body"),
        "public ingress must use only IPv4 CIDR rules and TCP")
for port in (80, 443):
    matching = [rule for rule in ingress_rules if f"FromPort: {port}" in rule]
    require(len(matching) == 1 and f"ToPort: {port}" in matching[0]
            and "IpProtocol: tcp" in matching[0] and "CidrIp: 0.0.0.0/0" in matching[0],
            f"only public IPv4 TCP {port} ingress is allowed")
for forbidden_port in (22, 4317, 4318):
    require(f"FromPort: {forbidden_port}" not in ingress.group("body")
            and f"ToPort: {forbidden_port}" not in ingress.group("body"),
            f"public ingress on TCP {forbidden_port} is prohibited")
egress_rules = re.findall(r"(?ms)^        - Description:.*?(?=^        - Description:|\Z)", egress.group("body"))
require(len(egress_rules) == 1 and "IpProtocol: tcp" in egress_rules[0]
        and "FromPort: 443" in egress_rules[0] and "ToPort: 443" in egress_rules[0]
        and "CidrIp: 0.0.0.0/0" in egress_rules[0]
        and re.findall(r"(?m)^          IpProtocol: (.+)$", egress.group("body")) == ["tcp"]
        and re.findall(r"(?m)^          CidrIp: (.+)$", egress.group("body")) == ["0.0.0.0/0"]
        and "CidrIpv6:" not in egress.group("body") and "IpProtocol: -1" not in security_group,
        "only explicit TCP 443 egress to IPv4 Internet is allowed")

instance = resource_blocks["AppInstance"]
require("Type: AWS::EC2::Instance" in instance and "ImageId: !Ref AmiId" in instance
        and "InstanceType: !Ref InstanceType" in instance
        and "IamInstanceProfile: !Ref OsaInstanceProfile" in instance,
        "exactly one app instance must use supplied runtime parameters and the app-owned profile")
require("AssociatePublicIpAddress: false" in instance and "KeyName:" not in instance
        and "MapPublicIpOnLaunch" not in instance,
        "the instance must not use an SSH key or automatic public IPv4 assignment")
require(len(re.findall(r"(?m)^        - DeviceIndex:", instance)) == 1,
        "the instance must have exactly one network interface")
require("AWS::EC2::EBS" not in resource_body and "AWS::EC2::Volume" not in resource_body
        and "AWS::EC2::Snapshot" not in resource_body and "AWS::Backup::" not in resource_body,
        "no application data volumes, snapshots, or backups may be created")
require(re.search(r"(?m)^\s*OSA_IMAGE=\$\{RepositoryUri\}@sha256:\$\{ImageDigest\}$", instance) is not None
        and re.search(r"(?m)^\s*OSA_VERSION=\$\{ReleaseVersion\}$", instance) is not None
        and re.search(r"(?m)^\s*OSA_ENVIRONMENT=\$\{Environment\}$", instance) is not None
        and "${RepositoryUri}@sha256:${ImageDigest}" in instance
        and "docker compose" in instance and "image: ${!OSA_IMAGE}" in instance,
        "instance user data must run the digest-pinned release with release version metadata through Compose")
require("amazon-ecr-credential-helper" in instance and "ecr-login" in instance
        and "AWS_ECR_DISABLE_CACHE=true" in instance
        and "docker login" not in instance and "get-login-password" not in instance
        and "FROM " not in instance and "docker build" not in instance,
        "ECR pulls must use the instance profile helper without storing tokens or building images")
require("caddy:2.10.2-alpine" in instance and "reverse_proxy app:8000" in instance
        and "redir https://{$PUBLIC_HOSTNAME}{uri} permanent" in instance
        and "condition: service_healthy" in instance
        and "restart: unless-stopped" in instance and "Restart=always" in instance,
        "Caddy must be pinned, proxy the supplied hostname, redirect HTTP, and wait for a healthy app")
require(
    "{$CADDY_AUTH_BLOCK}" in instance
    and re.findall(r"(?m)^\s*CADDY_AUTH_BLOCK=(.*)$", instance) == [""]
    and instance.count("basic_auth") == 2
    and '*"basic_auth"*)' in instance
    and not re.search(r"(?m)^\s*basic_auth\s*\{", instance),
    "the EC2 runtime must use an empty non-secret auth placeholder and reject a dev deployment without runtime Basic Auth",
)
start_marker = "cat > /opt/osa/start_osa_compose.sh <<'STARTCOMPOSE'"
end_marker = "              STARTCOMPOSE"
require(start_marker in instance and end_marker in instance, "user data must install the tested runtime wrapper")
embedded_wrapper = instance.split(start_marker, 1)[1].split(end_marker, 1)[0]
for contract in (
    "aws ssm get-parameter", "--name /osa/dev/caddy/auth", "--query Parameter.Type",
    "--with-decryption",
    "development:false)", "production:true)", "2>/dev/null",
    "exec docker compose --env-file /opt/osa/.env -f /opt/osa/compose.yaml up --remove-orphans",
):
    require(contract in embedded_wrapper, f"embedded runtime wrapper must satisfy contract: {contract}")
require(
    'parameter_type="$(aws ssm get-parameter' in embedded_wrapper
    and '!= "SecureString"' in embedded_wrapper,
    "embedded runtime wrapper must reject an ordinary String parameter",
)
require(
    "CADDY_AUTH_BLOCK=\n" in instance
    and "EnvironmentFile=/opt/osa/.env" in instance
    and "ExecStart=/opt/osa/start_osa_compose.sh" in instance,
    "production must not retrieve auth and systemd must pass only the empty env-file placeholder to the wrapper",
)
require("AWS::EC2::EIP" in resource_blocks["AppElasticIp"]
        and "Domain: vpc" in resource_blocks["AppElasticIp"]
        and "InstanceId: !Ref AppInstance" in resource_blocks["AppElasticIpAssociation"]
        and "AllocationId: !GetAtt AppElasticIp.AllocationId" in resource_blocks["AppElasticIpAssociation"]
        and "EIP:" not in resource_blocks["AppElasticIpAssociation"],
        "one Elastic IP must be associated with the sole app instance")
for forbidden in ("Password=", "Password:", "Secret=", "Secret:", "Token=", "Token:", "Credential="):
    require(forbidden not in instance, f"user data must not contain secret material ({forbidden})")
environment_assignments = re.findall(r"(?im)^\s*([A-Z][A-Z0-9_]*)\s*[:=]\s*\S+", instance)
require(
    not any(re.search(r"(?:^|_)(?:PASSWORD|SECRET|TOKEN|CREDENTIALS?|ACCESS_KEY)(?:_|$)", name, re.IGNORECASE)
            for name in environment_assignments),
    "user data must not assign secret or credential values",
)
for forbidden in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "aws ecr get-login-password", "docker login"):
    require(forbidden.lower() not in instance.lower(), f"user data must not contain credentials or out-of-scope auth config ({forbidden})")

outputs = re.search(r"(?ms)^Outputs:\n(?P<body>.*)\Z", text)
require(outputs is not None, "Outputs section is required")
output_body = outputs.group("body")
output_names = re.findall(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):\n", output_body)
approved_outputs = ["Environment", "ImageReference", "ReleaseVersion", "ReleaseParameterName", "InstanceId",
                    "PublicIp", "PublicEndpoint", "PublicHostname", "ImageDigest"]
require(output_names == approved_outputs,
        "outputs must contain only stable non-secret release/runtime verification values")
output_blocks = dict(
    re.findall(
        r"(?ms)^  ([A-Za-z][A-Za-z0-9]*):\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)",
        output_body,
    )
)
require(
    set(output_blocks) == set(approved_outputs)
    and len(output_blocks) == len(approved_outputs),
    "exactly the approved stable outputs must be declared",
)


def output_value(output_name: str, block: str) -> str:
    lines = block.splitlines()
    value_indexes = [index for index, line in enumerate(lines) if line.startswith("    Value:")]
    require(len(value_indexes) == 1, f"{output_name} must have exactly one Value")
    index = value_indexes[0]
    line = lines[index]
    inline = line[len("    Value:"):].strip()
    if inline:
        return f"Value: {inline}"
    value_lines = ["Value:"]
    for nested_line in lines[index + 1:]:
        if nested_line.strip() and len(nested_line) - len(nested_line.lstrip()) <= 4:
            break
        if nested_line.strip():
            require(nested_line.startswith("      "), f"{output_name} Value must be a valid nested intrinsic")
            value_lines.append(nested_line[4:])
    return "\n".join(value_lines)


expected_output_values = {
    "Environment": "Value: !Ref Environment",
    "ImageReference": (
        'Value:\n'
        '  Fn::Sub:\n'
        '    - "${RepositoryUri}@sha256:${Digest}"\n'
        '    - RepositoryUri:\n'
        '        Fn::ImportValue: osa-foundation-RepositoryUri\n'
        '      Digest: !Ref ImageDigest'
    ),
    "ReleaseVersion": "Value: !Ref ReleaseVersion",
    "ReleaseParameterName": "Value: !Ref ReleaseImageMetadataParameter",
    "InstanceId": "Value: !Ref AppInstance",
    "PublicIp": "Value: !Ref AppElasticIp",
    "PublicEndpoint": 'Value: !Sub "https://${PublicHostname}"',
    "PublicHostname": "Value: !Ref PublicHostname",
    "ImageDigest": "Value: !Ref ImageDigest",
}
for output_name, expected_value in expected_output_values.items():
    require(
        output_value(output_name, output_blocks[output_name]) == expected_value,
        f"{output_name} output must retain its exact approved value contract",
    )
for forbidden in ("Password", "Hash", "Token", "Credential", "Secret", "UserData"):
    require(forbidden not in output_body, f"outputs must not expose {forbidden.lower()} values")

# Exercise representative parameter values without AWS access.
for environment_value, expected_path in (("development", "/osa/dev/release/image"),
                                         ("production", "/osa/prod/release/image")):
    require(environment_value in environment, f"validator must accept {environment_value}")
    require(expected_path in resource_body, f"validator must map {environment_value} to {expected_path}")
for value in ("0" * 64, "a" * 64, "0123456789abcdef" * 4):
    require(re.fullmatch(r"[a-f0-9]{64}", value) is not None, "valid digest sample rejected")
for value in ("latest", "repo:latest", "sha256:" + "a" * 64, "A" * 64, "a" * 63, "a" * 65, ""):
    require(re.fullmatch(r"[a-f0-9]{64}", value) is None, f"invalid image digest sample accepted: {value}")
for value in ("20261026-abc1234", "1.2.3", "release_candidate+4"):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", value) is not None, "valid release version rejected")
for value in ("", " leading", "contains space", "x" * 129):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", value) is None,
            f"invalid release version accepted: {value}")
for value in ("ami-0123456789abcdef0", "ami-0123abcd"):
    require(re.fullmatch(r"ami-[a-f0-9]{8,17}", value) is not None, "valid AMI ID sample rejected")
for value in ("latest", "ami-ABCDEF12", "ami-1234", "ami-" + "a" * 18):
    require(re.fullmatch(r"ami-[a-f0-9]{8,17}", value) is None, f"invalid AMI ID sample accepted: {value}")
for value in ("t3.small", "m7i.2xlarge"):
    require(re.fullmatch(r"[a-z][0-9][a-z0-9]*\.[a-z0-9]+", value) is not None, "valid EC2 instance type rejected")
for value in ("latest", "t3", "T3.small", "t3.small.extra"):
    require(re.fullmatch(r"[a-z][0-9][a-z0-9]*\.[a-z0-9]+", value) is None,
            f"invalid EC2 instance type accepted: {value}")
hostname_pattern = r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
def valid_hostname(value: str) -> bool:
    return len(value) <= 253 and re.fullmatch(hostname_pattern, value) is not None

for value in ("dev.example.com", "sales-1.example.co.uk"):
    require(valid_hostname(value), "valid hostname sample rejected")
long_hostname = ".".join(["a" * 63] * 4)
for value in ("localhost", "-dev.example.com", "dev-.example.com", "dev..example.com", "dev.example.com.", long_hostname):
    require(not valid_hostname(value), f"invalid hostname accepted: {value}")

readme = Path("deploy/README.md").read_text(encoding="utf-8")
doc = readme.lower()
for phrase, message in (
    ("osa-application.yaml", "README must document the one shared application template"),
    ("osa-foundation-repositoryuri", "README must document the foundation repository export"),
    ("/osa/dev/release/image", "README must document the development metadata parameter path"),
    ("/osa/prod/release/image", "README must document the production metadata parameter path"),
    ("non-secret", "README must distinguish release metadata from secrets"),
    ("securestring", "README must distinguish release metadata from SecureString credentials"),
    ("#240", "README must document runtime resources for issue #240"),
    ("#242", "README must assign secret injection to issue #242"),
    ("systems manager session manager", "README must document no-SSH Systems Manager administration"),
    ("a record", "README must document operator-managed DNS A-record setup"),
    ("ephemeral", "README must document the ephemeral application-data boundary"),
    ("offline checks", "README must document the limits of offline validation"),
):
    require(phrase in doc, message)
for url in (
    "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resources-section-structure.html",
    "https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ssm-parameter.html",
):
    require(url in readme, f"README must cite the AWS pattern source: {url}")

print("Application template import, parameter, resource, output, documentation, and offline parameter assertions passed.")
