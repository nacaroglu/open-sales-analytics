#!/usr/bin/env python3
"""Offline assertions for the osa-dev and osa-prod deployment manifests."""
from pathlib import Path
import json
import re
import sys

MANIFEST_DIR = Path("deploy/cloudformation/environments")
TEMPLATE = Path("deploy/cloudformation/osa-application.yaml")
EXPECTED = {
    "osa-dev.json": {
        "StackName": "osa-dev",
        "Environment": "development",
        "ExecutionRoleOutput": "DevApplicationExecutionRoleArn",
        "DeployRoleOutput": "DevDeployRoleArn",
    },
    "osa-prod.json": {
        "StackName": "osa-prod",
        "Environment": "production",
        "ExecutionRoleOutput": "ProdApplicationExecutionRoleArn",
        "DeployRoleOutput": "ProductionPromotionRoleArn",
    },
}
EXPECTED_KEYS = {
    "StackName",
    "TemplateFile",
    "Parameters",
    "RuntimeInputs",
    "FoundationRoleOutputs",
}
EXPECTED_RUNTIME_INPUTS = ["ImageDigest", "ReleaseVersion"]


def fail(message: str) -> None:
    print(f"::error::{message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


manifest_paths = sorted(MANIFEST_DIR.glob("*.json"))
require(
    [path.name for path in manifest_paths] == sorted(EXPECTED),
    "environment manifests must be exactly osa-dev.json and osa-prod.json",
)
require(TEMPLATE.is_file(), f"shared application template is missing: {TEMPLATE}")

template_text = TEMPLATE.read_text(encoding="utf-8")
parameter_section = re.search(
    r"(?ms)^Parameters:\n(?P<body>.*?)(?=^Conditions:|^Resources:|\Z)",
    template_text,
)
require(parameter_section is not None, "application template Parameters section is missing")
template_parameters = set(
    re.findall(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):\n", parameter_section.group("body"))
)
require(
    template_parameters == {"Environment", "ImageDigest", "ReleaseVersion"},
    "application template input parameters do not match the manifest contract",
)
require(
    'AllowedPattern: "^[a-f0-9]{64}$"' in template_text
    and 'AllowedPattern: "^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$"' in template_text,
    "application template must enforce the immutable digest and readable release-version contracts",
)

manifest_data: dict[str, dict[str, object]] = {}
for filename, expected in EXPECTED.items():
    path = MANIFEST_DIR / filename
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{path} must be valid readable JSON: {exc}")
    require(isinstance(manifest, dict), f"{path} must contain a JSON object")
    require(
        set(manifest) == EXPECTED_KEYS,
        f"{path} fields must match the explicit manifest allowlist",
    )
    for field in ("StackName", "TemplateFile"):
        require(isinstance(manifest[field], str), f"{path} {field} must be a string")
    require(manifest["StackName"] == expected["StackName"],
            f"{path} must target exactly {expected['StackName']}")
    template_path = (path.parent / manifest["TemplateFile"]).resolve()
    require(template_path == TEMPLATE.resolve() and template_path.is_file(),
            f"{path} must resolve to the shared osa-application.yaml template")
    parameters = manifest["Parameters"]
    require(
        isinstance(parameters, dict)
        and set(parameters) == {"Environment"}
        and parameters["Environment"] == expected["Environment"],
        f"{path} must set only its matching fixed Environment parameter",
    )
    require(
        manifest["RuntimeInputs"] == EXPECTED_RUNTIME_INPUTS,
        f"{path} must require runtime ImageDigest and ReleaseVersion inputs in template order",
    )
    role_outputs = manifest["FoundationRoleOutputs"]
    require(
        isinstance(role_outputs, dict)
        and set(role_outputs) == {"CloudFormationExecutionRole", "GitHubDeployRole"}
        and role_outputs["CloudFormationExecutionRole"] == expected["ExecutionRoleOutput"]
        and role_outputs["GitHubDeployRole"] == expected["DeployRoleOutput"],
        f"{path} must pair the exact environment-specific foundation execution/deploy role output keys",
    )
    manifest_data[filename] = manifest

dev_manifest = manifest_data["osa-dev.json"]
prod_manifest = manifest_data["osa-prod.json"]
require(
    dev_manifest["TemplateFile"] == prod_manifest["TemplateFile"]
    and dev_manifest["RuntimeInputs"] == prod_manifest["RuntimeInputs"],
    "development and production must share one template and the same runtime parameter names",
)
require(
    dev_manifest["Parameters"] != prod_manifest["Parameters"]
    and dev_manifest["FoundationRoleOutputs"] != prod_manifest["FoundationRoleOutputs"],
    "development and production manifests must not select the same environment or role pair",
)

readme = Path("deploy/README.md").read_text(encoding="utf-8").lower()
for phrase, message in (
    ("osa-dev.json", "README must document the development manifest"),
    ("osa-prod.json", "README must document the production manifest"),
    ("osa-application.yaml", "README must identify the shared application template"),
    ("devapplicationexecutionrolearn", "README must document the development execution-role output key"),
    ("prodapplicationexecutionrolearn", "README must document the production execution-role output key"),
    ("devdeployrolearn", "README must document the development GitHub deploy-role output key"),
    ("productionpromotionrolearn", "README must document the production GitHub deploy-role output key"),
    ("imagedigest", "README must document the runtime image digest input"),
    ("releaseversion", "README must document the runtime release version input"),
    ("production promotion must reuse that exact supplied digest", "README must document unchanged digest promotion"),
    ("create osa-foundation before either application stack", "README must document foundation-first ordering"),
    ("delete the application stacks before foundation teardown", "README must document app-first teardown ordering"),
):
    require(phrase in readme, message)

print("Environment manifest schema, template, environment, role, documentation, and runtime-input assertions passed.")
