# Развертывание в AWS (CloudFormation)

[English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

> Перевод документа [на английском языке](README.md), который является источником истины. Версия синхронизации: `045796b0c7bbdd21520ccce1c7972495aab929f8` от `2026-10-22`.

`cloudformation.yaml` создает репозиторий ECR, сервис ECS Fargate (одна задача) и общедоступный Application Load
Balancer. Наборы данных хранятся на временном диске задачи и теряются при ее перезапуске; это соответствует принятой
в приложении модели временных наборов данных с сохранением по мере возможности. Не увеличивайте `DesiredCount` выше 1:
каждый набор данных представляет собой локальный файл DuckDB.

Потребуются AWS CLI с настроенными учетными данными и Docker. Выберите VPC с двумя общедоступными подсетями
(подойдет VPC по умолчанию).

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

Необязательные параметры: `PublicDemoMode=true`, `DatasetTtlHours`, `CertificateArn` (включает HTTPS и перенаправляет
HTTP). Без сертификата сайт работает по обычному HTTP, поэтому загруженные данные о продажах передаются без шифрования;
для реального использования настройте сертификат. Чтобы развернуть новый образ, отправьте его в репозиторий и выполните
`aws ecs update-service --force-new-deployment`. Удалите стек командой `aws cloudformation delete-stack`; перед этим
очистите репозиторий ECR.


## Развертывание Docker Compose

Файл переопределения Compose запускает образ приложения с неизменяемым digest за Caddy. Передайте полный адрес образа, публичное имя хоста, среду и версию во время запуска. Для разработки также требуется блок Caddy basic-auth с именем пользователя и хешем пароля; создайте хеш во время запуска и передайте блок, не добавляя его в репозиторий. В production этот блок оставляют пустым и включают публичный демонстрационный режим.

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

Для настроек production задайте `CADDY_AUTH_BLOCK=''`, `PUBLIC_DEMO_MODE=true` и `OSA_ENVIRONMENT=production`. Хеш пароля передается во время запуска; не помещайте учетные данные или хеши в файлы Compose, историю команд или журналы CI.


## Shared foundation stack

The separate `deploy/cloudformation/osa-foundation.yaml` template creates the shared VPC and subnets, immutable scan-on-push ECR repository, GitHub Actions OIDC provider, image build/push role, and foundation execution role. It creates no security groups or ingress rules. Private route tables have no direct internet-gateway route.

### Parameters and exports

Set `AvailabilityZone1` and `AvailabilityZone2` to distinct AZs. `VpcCidr`, the two `PublicSubnet*Cidr` values, and the two `PrivateSubnet*Cidr` values define non-overlapping network ranges; defaults are `10.40.0.0/16` and four `/20` subnets. Set `GitHubOwner` and `GitHubRepository`; `GitHubMainBranch` defaults to `main` and the OIDC subject matches that exact branch. `RepositoryName` defaults to `open-sales-analytics`.

Deploy as `osa-foundation` to use stable stack-qualified exports: `osa-foundation-VpcId`, `osa-foundation-PublicSubnetAz1Id`, `osa-foundation-PublicSubnetAz2Id`, `osa-foundation-PrivateSubnetAz1Id`, `osa-foundation-PrivateSubnetAz2Id`, `osa-foundation-PublicSubnetIds`, `osa-foundation-PrivateSubnetIds`, `osa-foundation-RepositoryArn`, `osa-foundation-RepositoryUri`, `osa-foundation-OidcProviderArn`, `osa-foundation-BuildRoleArn`, `osa-foundation-FoundationExecutionRoleArn`, `osa-foundation-StackName`, and `osa-foundation-Region`. Import values in later templates with `Fn::ImportValue`; use `Fn::Split` for the comma-separated subnet lists.

The GitHub trust requires the exact owner/repository/branch subject and `sts.amazonaws.com` audience; it grants no long-lived credentials. See [GitHub's AWS OIDC guide](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

### Create and validate

Creating named IAM roles requires `CAPABILITY_NAMED_IAM`. The caller needs permission to create the declared resources and pass the foundation execution role to CloudFormation.

```sh
REGION=eu-central-1; STACK=osa-foundation
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file deploy/cloudformation/osa-foundation.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides AvailabilityZone1=eu-central-1a AvailabilityZone2=eu-central-1b \
    GitHubOwner=OWNER GitHubRepository=open-sales-analytics
```

Validate locally with the signed, pinned AWS `cfn-validate` binary and the repository's static assertions:

```sh
cfn-validate --strict deploy/cloudformation/osa-foundation.yaml
python3 scripts/validate_foundation_template.py
```

The validator bundles schemas and rules, so the validation itself needs no AWS credentials or network. CI verifies the binary's SHA-256 and detached signature before running it; CI never deploys this template. See the [AWS CloudFormation validation guide](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html) and [AWS validator signature instructions](https://github.com/aws-cloudformation/cloudformation-validate/blob/main/INSTALLATION.md).

### Delete and cleanup

Delete downstream stacks before `osa-foundation`; CloudFormation prevents deleting exports still imported by another stack. Then use `aws cloudformation delete-stack`. Remove ECR images explicitly before cleanup. Bounded lifecycle and empty-on-delete behavior are deferred to issue #236. Review parameters, IAM capabilities, and the AWS change set before any deployment; offline validation does not confirm regional AZ or CIDR availability. See [CloudFormation resource documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html).
