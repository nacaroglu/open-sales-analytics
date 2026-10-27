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


## Общий foundation-стек

Отдельный шаблон `deploy/cloudformation/osa-foundation.yaml` создаёт общую VPC и подсети, репозиторий ECR с неизменяемыми тегами и проверкой при отправке, OIDC-провайдер GitHub Actions, роль сборки и отправки образов и роль выполнения foundation-стека. Шаблон не создаёт группы безопасности или правила входящего трафика. В таблицах маршрутизации частных подсетей нет прямого маршрута к интернет-шлюзу.

### Параметры и экспорты

Выберите разные AZ для `AvailabilityZone1` и `AvailabilityZone2`. `VpcCidr`, две величины `PublicSubnet*Cidr` и две `PrivateSubnet*Cidr` задают непересекающиеся диапазоны; значения по умолчанию — `10.40.0.0/16` и четыре подсети `/20`. Укажите `GitHubOwner` и `GitHubRepository`; `GitHubMainBranch` по умолчанию равен `main`, а OIDC subject разрешает только эту ветку. `RepositoryName` по умолчанию равен `open-sales-analytics`.

При создании стека с именем `osa-foundation` появляются стабильные экспорты с именем стека: `osa-foundation-VpcId`, `osa-foundation-PublicSubnetAz1Id`, `osa-foundation-PublicSubnetAz2Id`, `osa-foundation-PrivateSubnetAz1Id`, `osa-foundation-PrivateSubnetAz2Id`, `osa-foundation-PublicSubnetIds`, `osa-foundation-PrivateSubnetIds`, `osa-foundation-RepositoryArn`, `osa-foundation-RepositoryUri`, `osa-foundation-OidcProviderArn`, `osa-foundation-BuildRoleArn`, `osa-foundation-FoundationExecutionRoleArn`, `osa-foundation-StackName` и `osa-foundation-Region`. В последующих шаблонах используйте `Fn::ImportValue`, а для списков подсетей, разделённых запятыми, — `Fn::Split`.

Доверие GitHub требует точного owner/repository/branch subject и audience `sts.amazonaws.com`; долговременные учётные данные не создаются. См. [руководство GitHub по AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

### Создание и проверка

Для создания именованных IAM-ролей требуется `CAPABILITY_NAMED_IAM`. Поскольку шаблон сам создаёт роль `FoundationExecutionRoleArn`, первый запуск стека выполняется с учётными данными вызывающего пользователя; передавать её через `--role-arn` до создания нельзя. При последующем обновлении этого же стека получите выходное значение `FoundationExecutionRoleArn` и укажите его через `--role-arn`; вызывающему пользователю требуется разрешение `iam:PassRole` для этой роли. CloudFormation связывает её с будущими операциями над стеком. См. документацию AWS для [CreateStack](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateStack.html) и [UpdateStack](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html).

При первом развёртывании не указывайте `--role-arn`, так как роль ещё не создана. При последующем изменении этого foundation-стека получите `FoundationExecutionRoleArn` и передайте его обычной команде развёртывания вместе с изменением шаблона или параметров:
```sh
REGION=eu-central-1; STACK=osa-foundation
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file deploy/cloudformation/osa-foundation.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides AvailabilityZone1=eu-central-1a AvailabilityZone2=eu-central-1b \
    GitHubOwner=OWNER GitHubRepository=open-sales-analytics
```

Для локальной проверки используйте подписанный закреплённый бинарный файл AWS `cfn-validate` и статические проверки репозитория:
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

Валидатор содержит схемы и правила, поэтому сама проверка не требует доступа к сети или учётных данных AWS. CI проверяет SHA-256 и отдельную подпись бинарного файла; развёртывания в CI нет. См. [руководство AWS по проверке CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html) и [инструкции AWS по проверке подписи](https://github.com/aws-cloudformation/cloudformation-validate/blob/main/INSTALLATION.md).

### Удаление и очистка

Перед удалением `osa-foundation` удалите все дочерние стеки, импортирующие его экспорты: CloudFormation не удалит экспорт, пока он импортируется. Затем выполните `aws cloudformation delete-stack`. Перед очисткой явно удалите образы ECR. Ограничение жизненного цикла и очистка при удалении относятся к задаче #236. Перед развёртыванием проверьте параметры, IAM capabilities и набор изменений AWS; офлайн-проверка не подтверждает доступность AZ или CIDR в выбранном регионе. См. [документацию ресурсов CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html).

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
