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
