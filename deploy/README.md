# Deploy to AWS (CloudFormation)

Languages: [English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

`cloudformation.yaml` creates an ECR repository, an ECS Fargate service (one task) and a public Application Load
Balancer. Datasets live on the task's ephemeral disk and are lost when the task restarts; that matches the app's
best-effort, expiring datasets. Do not raise `DesiredCount` above 1: each dataset is a local DuckDB file.

Needs the AWS CLI with credentials, and Docker. Pick a VPC with two public subnets (the default VPC works).

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

Optional parameters: `PublicDemoMode=true`, `DatasetTtlHours`, `CertificateArn` (enables HTTPS and redirects HTTP).
Without a certificate the site is plain HTTP, so uploaded sales data travels unencrypted; set one for real use.
To ship a new image, push it and run `aws ecs update-service --force-new-deployment`.
Delete the stack with `aws cloudformation delete-stack`; empty the ECR repository first.

## Docker Compose deployment

The deployment Compose override runs the application image by immutable digest behind Caddy. Provide the complete
image reference, public hostname, environment, and release version at runtime. Development also requires a Caddy
basic-auth block containing a username and a password hash; generate the hash at runtime and inject the block without
committing it. Production leaves that block empty and enables the public demo mode.

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

For production, set `OSA_ENVIRONMENT=production`, `PUBLIC_DEMO_MODE=true`, and `CADDY_AUTH_BLOCK=''`.
The password hash is runtime input; do not put credentials or hashes in Compose files, shell history, or CI logs.
