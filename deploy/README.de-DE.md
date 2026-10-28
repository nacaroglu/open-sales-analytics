# Bereitstellung auf AWS (CloudFormation)

[English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

> Maßgeblich für die Richtigkeit dieser Übersetzung ist das [englische Dokument](README.md). Synchronisierungsrevision: `045796b0c7bbdd21520ccce1c7972495aab929f8` (2026-10-22).

`cloudformation.yaml` erstellt ein ECR-Repository, einen ECS-Fargate-Service (eine Task) und einen öffentlichen
Application Load Balancer. Datensätze liegen auf dem flüchtigen Datenträger der Task und gehen bei einem Neustart
verloren; das entspricht den nach bestem Bemühen gespeicherten, ablaufenden Datensätzen der Anwendung. Erhöhe
`DesiredCount` nicht über 1: Jeder Datensatz ist eine lokale DuckDB-Datei.

Benötigt werden die AWS CLI mit Zugangsdaten und Docker. Wähle eine VPC mit zwei öffentlichen Subnetzen (die
Standard-VPC ist geeignet).

```sh
REGION=eu-central-1; STACK=open-sales-analytics
VPC=vpc-xxxx; SUBNETS=subnet-aaaa,subnet-bbbb

# 1. Create everything with no task running (the repository is still empty)
aws cloudformation deploy --region $REGION --stack-name $STACK --template-file deploy/cloudformation.yaml \
  --capabilities CAPABILITY_IAM --parameter-overrides VpcId=$VPC SubnetIds=$SUBNETS DesiredCount=0

# 2. Build and push the image
REPO=$(aws cloudformation describe-stacks --region $REGION --stack-name $STACK \
  --query "Stacks[0].Outputs[?OutputKey=='RepositoryUri'].OutputValue" --output text)
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin ${REPO%%/*}
docker build -t $REPO:latest . && docker push $REPO:latest

# 3. Start the task
aws cloudformation deploy --region $REGION --stack-name $STACK --template-file deploy/cloudformation.yaml \
  --capabilities CAPABILITY_IAM --parameter-overrides VpcId=$VPC SubnetIds=$SUBNETS DesiredCount=1
aws cloudformation describe-stacks --region $REGION --stack-name $STACK --query "Stacks[0].Outputs"
```

Optionale Parameter: `PublicDemoMode=true`, `DatasetTtlHours`, `CertificateArn` (aktiviert HTTPS und leitet HTTP um).
Ohne Zertifikat verwendet die Site unverschlüsseltes HTTP, sodass hochgeladene Verkaufsdaten unverschlüsselt
übertragen werden; richte für den echten Einsatz ein Zertifikat ein. Um ein neues Image auszuliefern, pushe es und
führe `aws ecs update-service --force-new-deployment` aus. Lösche den Stack mit
`aws cloudformation delete-stack`; leere zuerst das ECR-Repository.


## Docker-Compose-Bereitstellung

Die Deployment-Compose-Override-Datei startet das Anwendungsimage mit unveränderlichem Digest hinter Caddy. Geben Sie den vollständigen Image-Verweis, den öffentlichen Hostnamen, die Umgebung und die Version zur Laufzeit an. Für die Entwicklung ist außerdem ein Caddy-basic-auth-Block mit Benutzername und Passwort-Hash erforderlich; erzeugen Sie den Hash zur Laufzeit und injizieren Sie den Block, ohne ihn einzuchecken. In Produktion bleibt der Block leer und der öffentliche Demomodus wird aktiviert.

```sh
export OSA_IMAGE='registry.example/open-sales-analytics@sha256:<64-character-image-digest>'
export OSA_HOSTNAME='sales.example.com'
export OSA_ENVIRONMENT=development
export OSA_VERSION=1.2.3
export PUBLIC_DEMO_MODE=false
read -rsp 'Password: ' password; printf '\n'
password_hash="$(docker run --rm --entrypoint caddy caddy:2.10.2 hash-password --plaintext "$password")"; unset password
export CADDY_AUTH_BLOCK="$(printf 'basic_auth {\n  demo %s\n}' "$password_hash")"
docker compose -f docker-compose.yaml -f docker-compose.deploy.yaml up -d
```

Geben Sie für Produktionseinstellungen `CADDY_AUTH_BLOCK=''` und `PUBLIC_DEMO_MODE=true` an und setzen Sie `OSA_ENVIRONMENT=production`. Der Passwort-Hash ist eine Laufzeiteingabe; speichern Sie keine Zugangsdaten oder Hashes in Compose-Dateien, im Shell-Verlauf oder in CI-Protokollen.


## Gemeinsamer Foundation-Stack

Die separate Vorlage `deploy/cloudformation/osa-foundation.yaml` erstellt das gemeinsame VPC und die Subnetze, ein ECR-Repository mit unveränderlichen Tags und Scan beim Push, den GitHub-Actions-OIDC-Provider, eine Image-Push-Rolle und die Ausführungsrolle für den Foundation-Stack. Sie erstellt keine Security Groups oder Ingress-Regeln. Private Routingtabellen haben keine direkte Route zum Internet Gateway.

### Parameter und Exporte

Wähle unterschiedliche AZs für `AvailabilityZone1` und `AvailabilityZone2`. `VpcCidr`, die beiden `PublicSubnet*Cidr`- und die beiden `PrivateSubnet*Cidr`-Werte legen nicht überlappende Netzwerkbereiche fest; Standardwerte sind `10.40.0.0/16` und vier `/20`-Subnetze. Setze `GitHubOwner` und `GitHubRepository`; `GitHubMainBranch` ist standardmäßig `main`, und der OIDC-Subject gilt genau für diesen Branch. `RepositoryName` ist standardmäßig `open-sales-analytics`.

Beim Deployment als `osa-foundation` entstehen stabile, durch den Stacknamen qualifizierte Exporte: `osa-foundation-VpcId`, `osa-foundation-PublicSubnetAz1Id`, `osa-foundation-PublicSubnetAz2Id`, `osa-foundation-PrivateSubnetAz1Id`, `osa-foundation-PrivateSubnetAz2Id`, `osa-foundation-PublicSubnetIds`, `osa-foundation-PrivateSubnetIds`, `osa-foundation-RepositoryArn`, `osa-foundation-RepositoryUri`, `osa-foundation-OidcProviderArn`, `osa-foundation-BuildRoleArn`, `osa-foundation-FoundationExecutionRoleArn`, `osa-foundation-StackName` und `osa-foundation-Region`. Verwende in späteren Templates `Fn::ImportValue`; für kommaseparierte Subnet-Listen nutze `Fn::Split`.

Die GitHub-Vertrauensregel verlangt exakt Repository-Eigentümer, Repository und Branch sowie die Audience `sts.amazonaws.com`; langlebige Zugangsdaten werden nicht ausgegeben. Siehe [GitHubs AWS-OIDC-Anleitung](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

### Erstellen und validieren

Für benannte IAM-Rollen ist `CAPABILITY_NAMED_IAM` erforderlich. Da das Template die Rolle `FoundationExecutionRoleArn` selbst erstellt, muss der erste Stack-Aufruf mit den Anmeldedaten des Aufrufers erfolgen; vor ihrer Erstellung kann sie nicht mit `--role-arn` übergeben werden. Bei einem späteren Update desselben Stacks kannst du die Ausgabe `FoundationExecutionRoleArn` abrufen und mit `--role-arn` angeben; dafür benötigt der Aufrufer `iam:PassRole` für diese Rolle. CloudFormation ordnet die Rolle künftigen Stack-Operationen zu. Siehe die AWS-Dokumentation zu [CreateStack](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateStack.html) und [UpdateStack](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html).

Beim ersten Deployment wird `--role-arn` ausgelassen, weil die Rolle noch nicht existiert. Bei einer späteren Änderung dieses Foundation-Stacks rufst du `FoundationExecutionRoleArn` ab und gibst es zusammen mit der Template- oder Parameteränderung an den üblichen Deployment-Befehl weiter:
```sh
REGION=eu-central-1; STACK=osa-foundation
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file deploy/cloudformation/osa-foundation.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides AvailabilityZone1=eu-central-1a AvailabilityZone2=eu-central-1b \
    GitHubOwner=OWNER GitHubRepository=open-sales-analytics
```

Prüfe lokal mit dem signierten, gepinnten AWS-Binary `cfn-validate` und den statischen Prüfungen des Repositorys:
```sh
EXECUTION_ROLE_ARN=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \\
  --query "Stacks[0].Outputs[?OutputKey=='FoundationExecutionRoleArn'].OutputValue" --output text)
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \\
  --template-file deploy/cloudformation/osa-foundation.yaml \\
  --capabilities CAPABILITY_NAMED_IAM --role-arn "$EXECUTION_ROLE_ARN" \\
  --parameter-overrides AvailabilityZone1=eu-central-1a AvailabilityZone2=eu-central-1b \\
    GitHubOwner=OWNER GitHubRepository=open-sales-analytics
```

```sh
cfn-validate --strict deploy/cloudformation/osa-foundation.yaml
python3 scripts/validate_foundation_template.py
```

Der Validator enthält Schemas und Regeln; die Validierung selbst benötigt weder AWS-Zugangsdaten noch Netzwerkzugriff. CI prüft SHA-256 und detached Signatur des Binaries und führt kein Deployment aus. Siehe den [AWS-CloudFormation-Validierungsleitfaden](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html) und die [AWS-Anleitung zur Signaturprüfung](https://github.com/aws-cloudformation/cloudformation-validate/blob/main/INSTALLATION.md).

### Löschen und bereinigen

Lösche alle nachgelagerten Stacks vor `osa-foundation`, die dessen Exporte importieren; CloudFormation verhindert das Entfernen eines noch importierten Exports. Führe danach `aws cloudformation delete-stack` aus. Entferne ECR-Images vor der Bereinigung explizit. Begrenzte Lifecycle-Regeln und Empty-on-Delete gehören zu Issue #236. Prüfe Parameter, IAM-Capabilities und den AWS-Änderungssatz vor einem Deployment; die Offline-Validierung bestätigt nicht, dass AZs oder CIDRs in der Region verfügbar sind. Siehe die [CloudFormation-Ressourcendokumentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html).

The shared `deploy/cloudformation/osa-application.yaml` is deployed twice as `osa-dev` and `osa-prod`. Both stacks use the same template and parameter names; select `Environment=development` or `Environment=production`, and supply `ImageDigest`, `ReleaseVersion`, `AmiId`, `InstanceType`, and `PublicHostname` at deploy time. `AmiId` must be an Amazon Linux 2023 image ID in the target region, and its architecture must match the selected instance type and image. `ImageDigest` is exactly 64 lowercase SHA-256 hexadecimal characters; `ReleaseVersion` is readable runtime metadata. `PublicHostname` is a dotted DNS name with valid labels. None of these inputs is an AWS credential or secret.

Each stack creates exactly one EC2 instance in `osa-foundation`'s first public subnet, disables automatic public-IP assignment, and attaches one stack-owned Elastic IP. Production uses `Ec2InstanceRole`; development uses `DevCaddyAuthEc2InstanceRole`. Both roles use a custom minimal Session Manager policy with only `ssm:UpdateInstanceInformation` and `ssmmessages:CreateControlChannel`, `ssmmessages:CreateDataChannel`, `ssmmessages:OpenControlChannel`, and `ssmmessages:OpenDataChannel`, without `AmazonSSMManagedInstanceCore` and its wildcard Parameter Store reads. Development additionally has `ssm:GetParameter` for only `arn:aws:ssm:<region>:<account>:parameter/osa/dev/caddy/auth` and `kms:Decrypt` only through regional Systems Manager, with the exact `PARAMETER_ARN` encryption context and `alias/aws/ssm` resource-alias condition. Production has no permission to retrieve or decrypt the auth parameter. The dev and prod CloudFormation execution roles may pass only their respective instance role to EC2. The instance has no SSH key pair. Administer it through Systems Manager Session Manager. AWS documents the minimal instance-profile policy for Session Manager at https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-create-iam-instance-profile.html.

The app security group allows only public IPv4 TCP 80 and 443. Port 80 supports ACME validation and redirects to HTTPS; TCP 443 serves the application through Caddy. Egress allows TCP 443 to public IPv4 for ECR API and S3 image-layer downloads, Systems Manager, certificate acquisition, and required runtime endpoints, plus TCP 4318 only to the imported private Collector security group for OTLP/HTTP. Security groups cannot filter AmazonProvidedDNS, so no broad DNS rule is declared. There is no public SSH or OTLP ingress, IPv6 rule, or Route 53 resource in this stack.

Before Caddy can obtain a public certificate, create an A record for the supplied hostname in your DNS provider or zone and point it to the stack's `PublicIp` output. The `PublicEndpoint` output is the corresponding HTTPS URL. Caddy and the application use version/digest-pinned images, wait for the application readiness check, and restart through Compose/systemd. The application image is pulled by the instance profile through the ECR credential helper with its disk cache disabled; no ECR password is written to user data or a file. The stack does not build images. Temporary DuckDB files remain on the instance/container filesystem. No application-data EBS volume, snapshot, backup, or durable mount is created; deleting the app stack removes its instance, root disk, profile, security group, and Elastic IP. Delete both application stacks before deleting `osa-foundation`.

The outputs include the instance ID, Elastic IP, hostname, HTTPS endpoint, image digest/reference, release version, and release metadata parameter name. The SSM release parameter is a non-secret `String`, not a `SecureString`; it records the immutable image reference only. Development uses `/osa/dev/release/image`, and production uses `/osa/prod/release/image`. Secret provisioning and runtime secret injection belong to #242.


CI derives each readable release version once from the UTC build time and the source commit: `YYYYMMDD-HHMMSS-<first seven lowercase commit-SHA characters>`. `backend/app/release_version.py` validates the full Git object ID and prints the version used by the image build; later delivery jobs consume that same output rather than generating a second version.

After all required CI jobs succeed for a push to `main`, the workflow publishes the exact validated image artifact to the immutable ECR repository using the release version as its tag. It then resolves and validates the ECR SHA-256 digest and exposes the repository URI, version, digest, and `repository@sha256:digest` reference as job outputs for the development deploy job. A collision with an existing immutable version fails the publish job; CI never overwrites that tag. Pull-request CI remains read-only and does not request AWS credentials.

If none of the three variables below is set, the publication job and the development deploy and verification jobs that depend on it are skipped. If any one is set, the job runs and fails when another is missing, so a partial configuration is never ignored.

Configure these non-secret GitHub Actions repository variables from the `osa-foundation` stack outputs before enabling main-branch publication:

- `OSA_AWS_REGION`: the foundation stack's AWS region.
- `OSA_BUILD_ROLE_ARN`: the `BuildRoleArn` output.
- `OSA_ECR_REPOSITORY_URI`: the `RepositoryUri` output.

The publish job exchanges GitHub's OIDC token for temporary credentials through the scoped build role. The role can authenticate to ECR, push images, and read image metadata only for the OSA repository so it can resolve the pushed digest; it cannot update CloudFormation stacks or pass roles. The [AWS credentials action's OIDC setup](https://github.com/aws-actions/configure-aws-credentials/blob/main/README.md#oidc) documents the GitHub permission and role trust requirements. Pull requests never receive these credentials.

After ECR publication succeeds on `main`, the workflow updates only `osa-dev` using the exact `repository@sha256:digest` and readable version outputs. The shared application template receives the digest and version separately, then writes the combined immutable image reference into stack metadata and runtime configuration. The deploy job does not build, retag, or look up a different image. It waits for the CloudFormation update to complete; readiness and the sample-dashboard smoke check are handled by issue #249.

Configure these additional non-secret repository variables before enabling automatic development deployment:

- `OSA_DEV_DEPLOY_ROLE_ARN`: the `DevDeployRoleArn` foundation output.
- `OSA_DEV_EXECUTION_ROLE_ARN`: the `DevApplicationExecutionRoleArn` foundation output.
- `OSA_AMI_ID`: an Amazon Linux 2023 AMI ID in `OSA_AWS_REGION`, compatible with the selected instance type.
- `OSA_INSTANCE_TYPE`: the development EC2 instance type.
- `OSA_DEV_HOSTNAME`: the development DNS hostname.

The GitHub OIDC development role can update and read only `osa-dev` and can pass only its development CloudFormation execution role. It has no create/delete-stack permission. Pull-request CI receives no OIDC token permission and never updates AWS resources.

### Development Caddy authentication

Provision `/osa/dev/caddy/auth` as an SSM Parameter Store `SecureString` before deploying the development application. Its value is a Caddy `basic_auth` block containing the selected username and a Caddy password hash. Generate the hash interactively with `caddy hash-password`; do not place a real hash or password in this guide, `.env`, user data, an image, shell history, CI output, or logs. Store the completed block in a local shell variable using silent input, then put it without printing the AWS response:

Use this sequence in your terminal; password input is silent, the AWS response is discarded, and all secret variables are unset afterward:

```sh
read -rsp 'Caddy password: ' caddy_password; printf '\n'
password_hash="$(docker run --rm --entrypoint caddy caddy:2.10.2 hash-password --plaintext "$caddy_password")"
unset caddy_password
read -rp 'Caddy username: ' caddy_username
CADDY_AUTH_BLOCK="$(printf 'basic_auth {\n  %s %s\n}' "$caddy_username" "$password_hash")"
unset password_hash caddy_username
aws ssm put-parameter --name /osa/dev/caddy/auth --type SecureString --value "$CADDY_AUTH_BLOCK" --overwrite >/dev/null
unset CADDY_AUTH_BLOCK
```

The default `aws/ssm` key is used. The development-only `DevCaddyAuthEc2InstanceRole` reads this one parameter at startup with `GetParameter --with-decryption`; its KMS grant is constrained by `kms:ViaService`, the exact SSM `PARAMETER_ARN` encryption context, and `kms:ResourceAliases=alias/aws/ssm`. The production instance role has no SSM or KMS auth-secret permission, and its startup wrapper never calls SSM. The wrapper keeps the retrieved block in process environment only, rejects missing, empty, malformed, inaccessible, or undecryptable values before Compose starts, and reports only generic errors. Rotation updates this same parameter, then restart the development service with `sudo systemctl restart osa-compose.service`. If startup fails, check parameter existence/type and the instance's SSM connectivity and role, correct the value, and restart; never retrieve the value into a terminal or diagnostic log. Systems Manager `SecureString` encryption and decryption behavior is described in the [AWS Parameter Store guide](https://docs.aws.amazon.com/systems-manager/latest/userguide/secure-string-parameter-kms-encryption.html); see also [KMS `kms:ViaService` conditions](https://docs.aws.amazon.com/kms/latest/developerguide/conditions-kms.html) and [KMS IAM resource scoping](https://docs.aws.amazon.com/kms/latest/developerguide/cmks-in-iam-policies.html).

Validate both environments offline using the signed, pinned strict CloudFormation validator and static assertions:

```sh
cfn-validate --strict deploy/cloudformation/osa-application.yaml \
  --exclude-resource-id AppInstance=W9010 \
  --parameter Environment=development \
  --parameter ImageDigest=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --parameter ReleaseVersion=20261027-dev \
  --parameter AmiId=ami-0123456789abcdef0 \
  --parameter InstanceType=t3.small \
  --parameter PublicHostname=dev.example.com
python3 scripts/validate_application_template.py
python3 scripts/validate_foundation_template.py
```

The `AppInstance=W9010` exclusion is narrow: the validator treats the required sample AMI parameter override as a literal AMI. The offline application assertion separately requires `ImageId: !Ref AmiId`, and CloudFormation's `AWS::EC2::Image::Id` parameter type validates the supplied ID at deployment. The production validation uses `Environment=production` and representative production values for the other parameters. CI runs the same checks with read-only repository permissions; validation does not assume AWS roles, call AWS APIs, create/update/delete stacks, or create credentials/artifacts. Offline checks verify template shape and security invariants, but cannot confirm that a supplied AMI or instance type exists in a selected region, that DNS has propagated, that Caddy can obtain a certificate, or that a public endpoint is reachable. AWS documents the [instance profile resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-iam-instanceprofile.html), [ECR image pulls](https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-pull-ecr-image.html), [security group rules and the AmazonProvidedDNS limitation](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html), [CloudFormation resource structure](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resources-section-structure.html), and [SSM parameter resource and tags](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ssm-parameter.html).


The checked-in environment manifests at deploy/cloudformation/environments/osa-dev.json and osa-prod.json describe the two independent stacks and both point to deploy/cloudformation/osa-application.yaml. Each fixes its matching Environment value and references the environment-specific CloudFormation execution-role and GitHub deploy-role output keys from osa-foundation; the output keys resolve to role ARNs at deployment time, so no account-specific ARN is stored here. ImageDigest and ReleaseVersion are required runtime inputs supplied by the later build/deploy or promotion workflow and are not stored in these manifests. Development deploys a tested immutable digest, and production promotion must reuse that exact supplied digest without rebuilding or retagging it. Create osa-foundation before either application stack, and delete the application stacks before foundation teardown.

Lokale und selbst gehostete Installationen verwenden standardmäßig `PUBLIC_DEMO_MODE=false` und behalten CSV-Uploads bei. In der Entwicklung muss `PUBLIC_DEMO_MODE=false` gesetzt sein und die Caddy-Konfiguration `basic_auth` enthalten; in Produktion muss `PUBLIC_DEMO_MODE=true` gesetzt und der Authentifizierungsblock leer sein.


### Verifizierung der Entwicklungsbereitstellung

After `deploy-dev` succeeds on `main`, `verify-dev` assumes the read-only `DevVerificationRole` exported as `osa-foundation-DevVerificationRoleArn` (configure repository variable `OSA_DEV_VERIFICATION_ROLE_ARN`). It reads only the `osa-dev` stack outputs and `/osa/dev/caddy/smoke-credential`. The credential is a SecureString in `username:password` format. Add a dedicated smoke user to `/osa/dev/caddy/auth` while preserving its existing human-user entries; use the procedure below. Keep both values out of GitHub secrets/variables, source control, command output, and logs.

The verifier checks the stack digest and release version against the published artifact, polls HTTPS `/health/ready` with normal TLS certificate and hostname validation for up to five minutes, creates the bundled sample through Basic Auth, checks its USD metadata and exact analytics, then deletes it using its dataset Bearer token. It masks the credential before further output. The verification job summary records environment, immutable image tag/version, digest, readiness, sample analytics, and temporary sample cleanup; it omits hostnames, account IDs, credentials, tokens, and raw command output. A failed verification summary names the failed stage and cleanup result. The deploy job also summarizes update success or failure; `CloudFormation rollback: NOT VERIFIED` means an operator should inspect the stack status. Any mismatch, timeout, or failed cleanup fails the job.

### Manuelle Produktionsfreigabe

Configure the repository-level variables `OSA_AWS_REGION`, `OSA_ECR_REPOSITORY_URI`, `OSA_PRODUCTION_SOURCE_READ_ROLE_ARN`, `OSA_PROD_PROMOTION_ROLE_ARN`, `OSA_PROD_EXECUTION_ROLE_ARN`, `OSA_AMI_ID`, `OSA_INSTANCE_TYPE`, and `OSA_PROD_HOSTNAME`. The source-read role is exported as `osa-foundation-ProductionSourceReadRoleArn`; the production promotion and execution roles use the exports documented above.

Create the GitHub repository Environment named `production`, enable required reviewers, and prevent self-review where the repository plan supports it. Add the intended operators as reviewers. The `promote-production.yml` workflow is started with Actions → Promote development release to production → Run workflow, using the `main` branch. It reads and validates the current dev digest/version with the read-only source role. The promotion job pauses for the `production` Environment approval before it obtains the production role credentials. After approval, it rereads dev and prod metadata, records the old prod release, and updates `osa-prod` to the current dev digest and version without building or retagging. Open the run summary to inspect source, target, and previous release metadata.

`Rollback: FAILED` means an operator must inspect production before another promotion.

The production promotion role's OIDC trust uses the exact subject `repo:<owner>/<repository>:environment:production` and audience `sts.amazonaws.com`. The source-read role has two exact subjects: the repository's configured main branch for preflight and the protected `production` Environment for a fresh source read after approval. It has only `cloudformation:DescribeStacks` on `osa-dev`. The production promotion role can update and read only `osa-prod` and pass only `ProdApplicationExecutionRole` to CloudFormation. Do not configure AWS access keys.

The Caddy Basic Auth exception applies only to `/api/datasets/` paths with a 22-character URL-safe dataset ID and a 43-character URL-safe Bearer header. FastAPI validates the token. Readiness, sample creation, and all other paths remain Basic Auth protected.

To add or rotate the dedicated smoke user without replacing the existing human user, run this in a private terminal with shell tracing disabled. It retrieves the existing auth block into a shell variable without printing it, appends one bcrypt entry, and writes both SecureStrings from mode-restricted temporary files. Choose a username not already in the block. The password is entered silently; use the same username and password for both parameters.


### Observability-Stack

Stellen Sie den Stack `osa-observability` nach foundation und vor den Anwendungs-Stacks bereit. Die Dev- und Prod-Stacks importieren die Collector-Sicherheitsgruppen-ID und verwalten jeweils nur die private OTLP-Regel, deren Quelle ihre eigene Anwendungssicherheitsgruppe ist. Löschen Sie zuerst die Anwendungs-Stacks, dann den Observability-Stack und zuletzt foundation. Der private Collector-Endpunkt und die Sicherheitsgruppen-ID werden exportiert; OTLP-Authentifizierungstoken liegen in SSM-`SecureString`-Parametern ihrer jeweiligen Umgebung.

Set the Grafana admin password in the environment's SSM SecureString parameter before deployment:

```sh
read -rsp 'Grafana admin password: ' grafana_password; printf '\n'
aws ssm put-parameter --name /osa/observability/grafana/admin-password \
  --type SecureString --value "$grafana_password" --overwrite >/dev/null
unset grafana_password
```

Deploy using the pinned config commit and region-specific Amazon Linux 2023 AMI:

```sh
aws cloudformation deploy --region "$REGION" --stack-name osa-observability \
  --template-file deploy/cloudformation/osa-observability.yaml \
  --capabilities CAPABILITY_IAM \
  --role-arn "$OSA_OBSERVABILITY_EXECUTION_ROLE_ARN" \
  --parameter-overrides AmiId="$OSA_AMI_ID" InstanceType=t3.small \
    GrafanaHostname="$OSA_GRAFANA_HOSTNAME" \
    GrafanaAdminParameterName=/osa/observability/grafana/admin-password \
    ObservabilityConfigRevision="$OSA_CONFIG_REVISION"
aws cloudformation describe-stacks --region "$REGION" --stack-name osa-observability \
  --query 'Stacks[0].Outputs'
```

```sh
set +x
umask 077
read -rp 'Smoke username: ' smoke_username
case "$smoke_username" in (*[!A-Za-z0-9_-]*|'') echo 'Invalid username' >&2; exit 1;; esac
read -rsp 'Smoke password: ' smoke_password; printf '\n'
smoke_hash="$(docker run --rm --entrypoint caddy caddy:2.10.2 hash-password --plaintext "$smoke_password")"
existing_auth="$(aws ssm get-parameter --name /osa/dev/caddy/auth --with-decryption --query Parameter.Value --output text)"
if printf '%s\n' "$existing_auth" | grep -Eq "^[[:space:]]+$smoke_username[[:space:]]"; then
  echo 'Smoke username already exists; choose another username' >&2; exit 1
fi
case "$existing_auth" in ('basic_auth {'*'}') ;; (*) echo 'Existing auth block is not the expected basic_auth form' >&2; exit 1;; esac
auth_body="${existing_auth%?}"
updated_auth="$(printf '%s\n  %s %s\n}' "$auth_body" "$smoke_username" "$smoke_hash")"
auth_file="$(mktemp)"; credential_file="$(mktemp)"
trap 'rm -f "$auth_file" "$credential_file"' EXIT
printf '%s' "$updated_auth" > "$auth_file"
printf '%s:%s' "$smoke_username" "$smoke_password" > "$credential_file"
aws ssm put-parameter --name /osa/dev/caddy/auth --type SecureString --value "file://$auth_file" --overwrite >/dev/null
aws ssm put-parameter --name /osa/dev/caddy/smoke-credential --type SecureString --value "file://$credential_file" --overwrite >/dev/null
unset smoke_password smoke_hash existing_auth auth_body updated_auth smoke_username
```

The update preserves all existing auth-block lines and adds only the dedicated smoke user. Do not print parameter values or enable shell tracing. The verifier reads the credential at runtime; it is never stored in GitHub configuration.

Technische Namen und Parameter bleiben wie in der Quelle unverändert: Stack `osa-foundation`; Ausgabe `osa-foundation-ObservabilityEc2InstanceRoleName`; Parameter `/osa/observability/grafana/admin-password`; KMS-Schlüsselalias `alias/aws/ssm` und Laufzeit-Entschlüsselungsbedingung `alias/aws/ssm`; Stacks `osa-dev` und `osa-prod`; Option `--role-arn`; Parametertyp `SecureString`; Ausgaben `ObservabilityExecutionRoleArn` und `ObservabilityEc2InstanceRoleName`; importierte `CollectorSecurityGroupId` und exportierte `CollectorSecurityGroupId`; `CollectorPrivateEndpoint`; Parameter `GrafanaHostname` und Konfigurationsfeld `GrafanaHostname`; `GrafanaPublicIp`; `GF_SERVER_ROOT_URL`; Geheimnispfad `/run`; sowie die ältere Vorlage `cloudformation-foundation`.

### Authenticated private OTLP ingestion

The app reads the private `CollectorPrivateEndpoint` export and sends OTLP/HTTP on TCP 4318. Its security group permits this traffic only to `CollectorSecurityGroupId`, and the Collector accepts app traffic through the matching security-group ingress. The endpoint is private; no public OTLP listener is created. The dev and prod tokens are environment-specific SSM `SecureString` parameters at `/osa/dev/observability/otlp-token` and `/osa/prod/observability/otlp-token`.

To rotate a token, set `OTLP_TOKEN_PARAMETER` to the matching dev or prod parameter path. Generate a fresh URL-safe token into a mode-restricted temporary file with `umask 077; TOKEN_FILE=$(mktemp); openssl rand -base64 32 | tr '+/' '-_' | tr -d '=' > "$TOKEN_FILE"`, then update the parameter with `aws ssm put-parameter --name "$OTLP_TOKEN_PARAMETER" --type SecureString --value "file://$TOKEN_FILE" --overwrite >/dev/null`. Do not print the token or use `--with-decryption` to inspect it. Through Session Manager, restart `osa-observability.service` on the Collector instance and `osa-compose.service` on the matching application instance; confirm both are active. Each service reloads its token from SSM at startup. Preflight checks verify that the environment parameter exists and has type `SecureString` without decrypting or exposing its value.

To verify authenticated private ingestion, connect to the matching application instance through Session Manager and run `docker compose --env-file /opt/osa/.env -f /opt/osa/compose.yaml exec -T app env PYTHONPATH=/app/backend OSA_ENVIRONMENT=development python -m app.telemetry_test_signal`; set `OSA_ENVIRONMENT=production` for prod. This emits a synthetic trace, metric, and log using the app's configured private endpoint and token file, without displaying the token. Confirm the command reports a successful flush, then use Grafana Explore to find `osa.synthetic.resource_identity` in Tempo, Prometheus, and Loki and verify `service.name`, `service.version`, and `deployment.environment.name`. Also confirm the environment's normal authenticated health check still succeeds. If a signal is missing, check the two service states, private endpoint and security-group rules, token parameter type, and service logs; logs must not include token values.

### Guarded Phase 4 teardown

The teardown deletes the four CloudFormation stacks in this order, waiting for each deletion to finish before starting the next:

1. `osa-dev`
2. `osa-prod`
3. `osa-observability`
4. `osa-foundation`

Run `.github/workflows/teardown-phase4.yml` manually from `main`; it has no push, pull-request or schedule trigger. CloudFormation owns resource deletion, including ECR empty-on-delete behavior. Do not manually delete resources or ECR images.

**Pre-teardown checklist.** Confirm every item before choosing `execute`:

- Retain anything you still need. Deleting `osa-foundation` force-deletes the ECR repository and its images, and the observability data volume is deleted with no snapshot or backup. Export evidence first (#270).
- Nothing outside the four stacks imports their exports. The preflight refuses to continue otherwise.
- All four stacks are in a stable state (not `*_IN_PROGRESS` and not a failed state that needs manual repair).
- The `osa-teardown` environment has required reviewers (see below) and the repository variables `OSA_AWS_REGION`, `OSA_TEARDOWN_AWS_ACCOUNT_ID`, `OSA_TEARDOWN_PREFLIGHT_ROLE_ARN` and `OSA_TEARDOWN_ROLE_ARN` are set. The preflight role must only inspect identity, target stack states, exports and importers. The delete role must have the same read access and be allowed to delete only the four target stacks.
- You are on `main` and the person approving is aware of the account and region being targeted.

**Approval configuration.** Repository changes cannot configure GitHub environment settings, so an administrator must create the `osa-teardown` environment, add required reviewers and restrict deployment branches to `main`. Verify the protection with the GitHub API (requires `gh` authenticated with repository administration read access):

```sh
gh api repos/nacaroglu/open-sales-analytics/environments/osa-teardown \
  | python3 scripts/verify_phase4_environment.py
```

The checker fails if the API response has no non-empty `required_reviewers` rule.

**Dry run.** The dry run lists the exact targets and order, makes no AWS calls and deletes nothing:

```sh
gh workflow run teardown-phase4.yml --ref main -f mode=dry-run
```

**Execution.** Execution requires the exact confirmation value `DELETE-PHASE4-OSA-RESOURCES`. The workflow runs a read-only preflight (account, region, stable stack states, outside importers), then waits at the protected `osa-teardown` environment so a reviewer can inspect the preflight result before approving deletion:

```sh
gh workflow run teardown-phase4.yml --ref main -f mode=execute -f confirmation=DELETE-PHASE4-OSA-RESOURCES
```

Approve the pending deployment in the workflow run. An absent stack is skipped. The workflow prints each stack outcome and a safe failure stage in `GITHUB_STEP_SUMMARY`, with no account IDs, ARNs or raw AWS responses.

**Recovery after a failure.** A failed delete or wait stops the run: later stacks are not touched, and the run is never retried automatically. Read the summary table to see which stacks are deleted, absent or not attempted, then use the failure stage:

- `workflow_setup`, `confirmation` or `region_configuration`: nothing was changed. The workflow or script stopped before AWS was used, for example because the confirmation value was not exact or a repository variable is missing. Rerun with the exact confirmation value and the repository variables set, including the correct `OSA_AWS_REGION`.
- `aws_identity`, `account_configuration`, `aws_client`, `aws_query`, `aws_response` or `aws_pagination`: the preflight could not verify the account or read AWS. Nothing was deleted. Check the role trust, the account ID variable and the region, then rerun.
- `stack_query`, `stack_state`, `export_query`, `import_query` or `outside_importer`: the preflight refused. Wait for in-progress stacks to settle, repair a failed stack, or remove the outside importer, then rerun.
- `delete_request` or `delete_wait`: CloudFormation failed to start or finish a stack deletion. Open the stack's events in the CloudFormation console to find the blocking resource, fix it, wait until the stack is stable (for example `DELETE_FAILED` after you remove the blocker), then rerun the workflow. Already deleted stacks are skipped.

If the summary shows `unknown`, treat it as a failed run of undetermined cause: read the workflow log, confirm the state of all four stacks in the CloudFormation console, and rerun only when they are stable.

Do not skip stacks or delete resources by hand to work around a failure. Final absence verification is tracked by #272.
