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

Each stack creates exactly one EC2 instance in `osa-foundation`'s first public subnet, disables automatic public-IP assignment, and attaches one stack-owned Elastic IP. It creates a path-scoped instance profile containing only the existing `osa-foundation` `Ec2InstanceRole`; that role retains only repository-scoped ECR image-pull permissions and `AmazonSSMManagedInstanceCore`. The dev and prod CloudFormation execution roles can manage only profiles under their matching `/osa-dev/` or `/osa-prod/` IAM path and may pass only the foundation EC2 role to EC2. The instance has no SSH key pair. Administer it through Systems Manager Session Manager or Run Command.

The app security group allows only public IPv4 TCP 80 and 443. Port 80 supports ACME validation and redirects to HTTPS; TCP 443 serves the application through Caddy. The only declared egress is TCP 443 to public IPv4 for ECR API and S3 image-layer downloads, Systems Manager, certificate acquisition, and required runtime endpoints. Security groups cannot filter AmazonProvidedDNS, so no broad DNS rule is declared. There is no public SSH or OTLP ingress, IPv6 rule, Route 53 resource, or private Collector route in this stack.

Before Caddy can obtain a public certificate, create an A record for the supplied hostname in your DNS provider or zone and point it to the stack's `PublicIp` output. The `PublicEndpoint` output is the corresponding HTTPS URL. Caddy and the application use version/digest-pinned images, wait for the application readiness check, and restart through Compose/systemd. The application image is pulled by the instance profile through the ECR credential helper with its disk cache disabled; no ECR password is written to user data or a file. The stack does not build images. Temporary DuckDB files remain on the instance/container filesystem. No application-data EBS volume, snapshot, backup, or durable mount is created; deleting the app stack removes its instance, root disk, profile, security group, and Elastic IP. Delete both application stacks before deleting `osa-foundation`.

The outputs include the instance ID, Elastic IP, hostname, HTTPS endpoint, image digest/reference, release version, and release metadata parameter name. The SSM release parameter is a non-secret `String`, not a `SecureString`; it records the immutable image reference only. Development uses `/osa/dev/release/image`, and production uses `/osa/prod/release/image`. Secret provisioning and runtime secret injection belong to #242.

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
