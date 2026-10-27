import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copyfile

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts" / "validate_observability_retention.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "osa_validate_observability_retention", VALIDATOR_PATH
)
assert VALIDATOR_SPEC is not None and VALIDATOR_SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)

RETENTION_WINDOW = VALIDATOR.RETENTION_WINDOW
is_expired = VALIDATOR.is_expired
validate_aws_storage_bootstrap = VALIDATOR.validate_aws_storage_bootstrap
validate_backend_configs = VALIDATOR.validate_backend_configs
validate_ebs_template = VALIDATOR.validate_ebs_template


def test_configured_backends_have_seven_day_retention_and_bounded_limits():
    assert validate_backend_configs(ROOT / "observability") == []


def test_data_older_than_seven_days_is_expired_but_boundary_data_remains():
    now = datetime(2026, 10, 27, 12, tzinfo=UTC)
    assert RETENTION_WINDOW == timedelta(days=7)
    assert not is_expired(now - timedelta(days=7), now)
    assert is_expired(now - timedelta(days=7, seconds=1), now)
    assert not is_expired(now, now)


def test_aws_backend_data_paths_share_the_attached_ebs_storage_root(tmp_path):
    for config in ("compose.yaml", "prometheus.yaml", "loki.yaml", "tempo.yaml"):
        copyfile(ROOT / "observability" / config, tmp_path / config)
    (tmp_path / "compose.aws.yaml").write_text(
        """services:
  prometheus:
    volumes:
      - ${OSA_STORAGE_ROOT:?required}/prometheus:/prometheus
  loki:
    volumes:
      - ${OSA_STORAGE_ROOT:?required}/loki:/loki
  tempo:
    volumes:
      - ${OSA_STORAGE_ROOT:?required}/tempo:/var/tempo
""",
        encoding="utf-8",
    )
    assert validate_backend_configs(tmp_path) == []


def test_observability_volume_requires_encryption_and_delete_policy(tmp_path):
    template = tmp_path / "osa-observability.yaml"
    template.write_text(
        """Resources:
  ObservabilityInstance:
    Type: AWS::EC2::Instance
    Properties:
      BlockDeviceMappings:
        - Ebs:
            Encrypted: true
            DeleteOnTermination: true
  TelemetryVolume:
    Type: AWS::EC2::Volume
    DeletionPolicy: Delete
    UpdateReplacePolicy: Delete
    Properties:
      Encrypted: true
      Size: 100
  TelemetryVolumeAttachment:
    Type: AWS::EC2::VolumeAttachment
    Properties:
      InstanceId: !Ref ObservabilityInstance
      VolumeId: !Ref TelemetryVolume
""",
        encoding="utf-8",
    )
    assert validate_ebs_template(template) == []


def test_observability_volume_rejects_unencrypted_or_retained_storage(tmp_path):
    template = tmp_path / "osa-observability.yaml"
    template.write_text(
        """Resources:
  TelemetryVolume:
    Type: AWS::EC2::Volume
    DeletionPolicy: Retain
    Properties:
      Encrypted: false
  TelemetryVolumeAttachment:
    Type: AWS::EC2::VolumeAttachment
    Properties:
      InstanceId: !Ref ObservabilityInstance
      VolumeId: !Ref TelemetryVolume
""",
        encoding="utf-8",
    )
    errors = validate_ebs_template(template)
    assert any("Encrypted" in error for error in errors)
    assert any("DeletionPolicy" in error for error in errors)
    assert any("UpdateReplacePolicy" in error for error in errors)


def test_aws_bootstrap_mounts_telemetry_paths_from_the_attached_ebs_volume(tmp_path):
    bootstrap = tmp_path / "bootstrap.sh"
    bootstrap.write_text(
        """storage_root=/srv/osa-observability
if ! mountpoint -q "$storage_root"; then
  mount "$storage_root"
fi
mkdir -p "$storage_root/prometheus" "$storage_root/loki" "$storage_root/tempo"
""",
        encoding="utf-8",
    )
    assert validate_aws_storage_bootstrap(bootstrap) == []


def test_telemetry_snapshots_and_backup_plans_are_rejected(tmp_path):
    template = tmp_path / "osa-observability.yaml"
    template.write_text(
        """Resources:
  TelemetryVolume:
    Type: AWS::EC2::Volume
    DeletionPolicy: Delete
    UpdateReplacePolicy: Delete
    Properties:
      Encrypted: true
      Size: 100
  TelemetryVolumeAttachment:
    Type: AWS::EC2::VolumeAttachment
    Properties:
      InstanceId: !Ref ObservabilityInstance
      VolumeId: !Ref TelemetryVolume
  TelemetrySnapshot:
    Type: AWS::EC2::Snapshot
""",
        encoding="utf-8",
    )
    assert "Telemetry snapshots and backups are not allowed" in validate_ebs_template(template)
