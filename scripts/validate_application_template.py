#!/usr/bin/env python3
"""Offline assertions for the parameterized OSA application release contract."""
from pathlib import Path
import re
import sys

TEMPLATE = Path("deploy/cloudformation/osa-application.yaml")
text = TEMPLATE.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        print(f"::error::{message}", file=sys.stderr)
        raise SystemExit(1)


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

parameters = re.search(r"(?ms)^Parameters:\n(?P<body>.*?)(?=^Conditions:|^Resources:|\Z)", text)
require(parameters is not None, "Parameters section is required")
parameter_names = re.findall(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):\n", parameters.group("body"))
require(
    set(parameter_names) == {"Environment", "ImageDigest", "ReleaseVersion"}
    and len(parameter_names) == 3,
    "the exact parameter set must be Environment, ImageDigest, and ReleaseVersion",
)

resources = re.search(r"(?ms)^Resources:\n(?P<body>.*?)(?=^Outputs:|\Z)", text)
require(resources is not None, "Resources section is required")
resource_body = resources.group("body")
resource_names = re.findall(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):\n    Type:", resource_body)
require(resource_names == ["ReleaseImageMetadataParameter"],
        "the sole application resource must be ReleaseImageMetadataParameter")
require(
    "    Type: AWS::SSM::Parameter" in resource_body
    and re.findall(r"(?m)^      Type: (.+)$", resource_body) == ["String"]
    and "SecureString" not in resource_body,
    "release metadata must be exactly one non-secret SSM String parameter",
)
require("Name: !If\n        - IsDevelopment\n        - /osa/dev/release/image\n        - /osa/prod/release/image" in resource_body,
        "parameter path must map development to /osa/dev and production to /osa/prod")
require("Fn::ImportValue: osa-foundation-RepositoryUri" in resource_body
        and '"${RepositoryUri}@sha256:${Digest}"' in resource_body
        and "Digest: !Ref ImageDigest" in resource_body,
        "parameter value must import the foundation repository URI and append the validated digest")
require("Project: open-sales-analytics" in resource_body and "Environment: !Ref Environment" in resource_body
        and "OSAStack: !If [IsDevelopment, osa-dev, osa-prod]" in resource_body,
        "the metadata parameter must carry project and environment-derived stack identity tags")
for forbidden in ("AWS::EC2::Volume", "AWS::EC2::Instance", "AWS::EC2::SecurityGroup",
                  "AWS::EC2::SecurityGroupIngress", "AWS::EC2::Snapshot", "AWS::Backup::",
                  "SecureString", "Password", "Credential"):
    require(forbidden not in resource_body, f"application baseline must not introduce {forbidden}")

outputs = re.search(r"(?ms)^Outputs:\n(?P<body>.*)\Z", text)
require(outputs is not None, "Outputs section is required")
output_body = outputs.group("body")
output_names = re.findall(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):\n", output_body)
require(output_names == ["Environment", "ImageReference", "ReleaseVersion", "ReleaseParameterName"],
        "only stable non-secret environment, image, version, and parameter-name outputs are allowed")
output_blocks = dict(
    re.findall(
        r"(?ms)^  ([A-Za-z][A-Za-z0-9]*):\n(?P<body>.*?)(?=^  [A-Za-z][A-Za-z0-9]*:\n|\Z)",
        output_body,
    )
)
require(
    set(output_blocks) == {"Environment", "ImageReference", "ReleaseVersion", "ReleaseParameterName"}
    and len(output_blocks) == 4,
    "exactly the four approved stable outputs must be declared",
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
}
for output_name, expected_value in expected_output_values.items():
    require(
        output_value(output_name, output_blocks[output_name]) == expected_value,
        f"{output_name} output must retain its exact approved value contract",
    )
for forbidden in ("Password", "Hash", "Token", "Credential", "Secret"):
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

readme = Path("deploy/README.md").read_text(encoding="utf-8")
doc = readme.lower()
for phrase, message in (
    ("osa-application.yaml", "README must document the one shared application template"),
    ("osa-foundation-repositoryuri", "README must document the foundation repository export"),
    ("/osa/dev/release/image", "README must document the development metadata parameter path"),
    ("/osa/prod/release/image", "README must document the production metadata parameter path"),
    ("non-secret", "README must distinguish release metadata from secrets"),
    ("securestring", "README must distinguish release metadata from SecureString credentials"),
    ("#240", "README must assign runtime resources to issue #240"),
    ("#242", "README must assign secret injection to issue #242"),
):
    require(phrase in doc, message)
for url in (
    "https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resources-section-structure.html",
    "https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ssm-parameter.html",
):
    require(url in readme, f"README must cite the AWS pattern source: {url}")

print("Application template import, parameter, resource, output, documentation, and offline parameter assertions passed.")
