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

Локальные и самостоятельно размещённые запуски по умолчанию используют `PUBLIC_DEMO_MODE=false` и сохраняют загрузку CSV. В разработке требуется `PUBLIC_DEMO_MODE=false` и директива `basic_auth` в конфигурации Caddy; в production требуется `PUBLIC_DEMO_MODE=true`, а блок аутентификации должен быть пустым.


### Проверка развертывания в dev

After `deploy-dev` succeeds on `main`, `verify-dev` assumes the read-only `DevVerificationRole` exported as `osa-foundation-DevVerificationRoleArn` (configure repository variable `OSA_DEV_VERIFICATION_ROLE_ARN`). It reads only the `osa-dev` stack outputs and `/osa/dev/caddy/smoke-credential`. The credential is a SecureString in `username:password` format. Add a dedicated smoke user to `/osa/dev/caddy/auth` while preserving its existing human-user entries; use the procedure below. Keep both values out of GitHub secrets/variables, source control, command output, and logs.

The verifier checks the stack digest and release version against the published artifact, polls HTTPS `/health/ready` with normal TLS certificate and hostname validation for up to five minutes, creates the bundled sample through Basic Auth, checks its USD metadata and exact analytics, then deletes it using its dataset Bearer token. It masks the credential before further output. The verification job summary records environment, immutable image tag/version, digest, readiness, sample analytics, and temporary sample cleanup; it omits hostnames, account IDs, credentials, tokens, and raw command output. A failed verification summary names the failed stage and cleanup result. The deploy job also summarizes update success or failure; `CloudFormation rollback: NOT VERIFIED` means an operator should inspect the stack status. Any mismatch, timeout, or failed cleanup fails the job.

### Ручное продвижение в production

Configure the repository-level variables `OSA_AWS_REGION`, `OSA_ECR_REPOSITORY_URI`, `OSA_PRODUCTION_SOURCE_READ_ROLE_ARN`, `OSA_PROD_PROMOTION_ROLE_ARN`, `OSA_PROD_EXECUTION_ROLE_ARN`, `OSA_AMI_ID`, `OSA_INSTANCE_TYPE`, and `OSA_PROD_HOSTNAME`. The source-read role is exported as `osa-foundation-ProductionSourceReadRoleArn`; the production promotion and execution roles use the exports documented above.

Create the GitHub repository Environment named `production`, enable required reviewers, and prevent self-review where the repository plan supports it. Add the intended operators as reviewers. The `promote-production.yml` workflow is started with Actions → Promote development release to production → Run workflow, using the `main` branch. It reads and validates the current dev digest/version with the read-only source role. The promotion job pauses for the `production` Environment approval before it obtains the production role credentials. After approval, it rereads dev and prod metadata, records the old prod release, and updates `osa-prod` to the current dev digest and version without building or retagging. Open the run summary to inspect source, target, and previous release metadata.

`Rollback: FAILED` means an operator must inspect production before another promotion.

The production promotion role's OIDC trust uses the exact subject `repo:<owner>/<repository>:environment:production` and audience `sts.amazonaws.com`. The source-read role has two exact subjects: the repository's configured main branch for preflight and the protected `production` Environment for a fresh source read after approval. It has only `cloudformation:DescribeStacks` on `osa-dev`. The production promotion role can update and read only `osa-prod` and pass only `ProdApplicationExecutionRole` to CloudFormation. Do not configure AWS access keys.

The Caddy Basic Auth exception applies only to `/api/datasets/` paths with a 22-character URL-safe dataset ID and a 43-character URL-safe Bearer header. FastAPI validates the token. Readiness, sample creation, and all other paths remain Basic Auth protected.

To add or rotate the dedicated smoke user without replacing the existing human user, run this in a private terminal with shell tracing disabled. It retrieves the existing auth block into a shell variable without printing it, appends one bcrypt entry, and writes both SecureStrings from mode-restricted temporary files. Choose a username not already in the block. The password is entered silently; use the same username and password for both parameters.


### Стек наблюдаемости

Разверните стек `osa-observability` после foundation и до стеков приложений. Стеки dev и prod импортируют идентификатор группы безопасности Collector и каждый управляет только своим частным правилом доступа OTLP, источником которого служит локальная группа безопасности приложения. При удалении сначала удалите стеки приложений, затем observability и в конце foundation. Частная конечная точка Collector и идентификатор группы безопасности экспортируются; токены аутентификации OTLP хранятся в параметрах SSM `SecureString` соответствующих сред.

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

Технические имена и параметры сохраняются без изменений: стек `osa-foundation`; выход `osa-foundation-ObservabilityEc2InstanceRoleName`; параметр `/osa/observability/grafana/admin-password`; псевдоним ключа KMS `alias/aws/ssm` и условие расшифрования во время выполнения `alias/aws/ssm`; стеки `osa-dev` и `osa-prod`; параметр `--role-arn`; тип параметра `SecureString`; выходы `ObservabilityExecutionRoleArn` и `ObservabilityEc2InstanceRoleName`; импортируемый `CollectorSecurityGroupId` и экспортируемый `CollectorSecurityGroupId`; `CollectorPrivateEndpoint`; параметр `GrafanaHostname` и поле конфигурации `GrafanaHostname`; `GrafanaPublicIp`; `GF_SERVER_ROOT_URL`; путь секрета `/run`; и прежний шаблон `cloudformation-foundation`.

### Authenticated private OTLP ingestion

The app reads the private `CollectorPrivateEndpoint` export and sends OTLP/HTTP on TCP 4318. Its security group permits this traffic only to `CollectorSecurityGroupId`, and the Collector accepts app traffic through the matching security-group ingress. The endpoint is private; no public OTLP listener is created. The dev and prod tokens are environment-specific SSM `SecureString` parameters at `/osa/dev/observability/otlp-token` and `/osa/prod/observability/otlp-token`.

To rotate a token, set `OTLP_TOKEN_PARAMETER` to the matching dev or prod parameter path. Generate a fresh URL-safe token into a mode-restricted temporary file with `umask 077; TOKEN_FILE=$(mktemp); openssl rand -base64 32 | tr '+/' '-_' | tr -d '=' > "$TOKEN_FILE"`, then update the parameter with `aws ssm put-parameter --name "$OTLP_TOKEN_PARAMETER" --type SecureString --value "file://$TOKEN_FILE" --overwrite >/dev/null`. Do not print the token or use `--with-decryption` to inspect it. Through Session Manager, restart `osa-observability.service` on the Collector instance and `osa-compose.service` on the matching application instance; confirm both are active. Each service reloads its token from SSM at startup. Preflight checks verify that the environment parameter exists and has type `SecureString` without decrypting or exposing its value.

To verify authenticated private ingestion, connect to the matching application instance through Session Manager and run `docker compose --env-file /opt/osa/.env -f /opt/osa/compose.yaml exec -T app env PYTHONPATH=/app/backend OSA_ENVIRONMENT=development python -m app.telemetry_test_signal`; set `OSA_ENVIRONMENT=production` for prod. This emits a synthetic trace, metric, and log using the app's configured private endpoint and token file, without displaying the token. Confirm the command reports a successful flush, then use Grafana Explore to find `osa.synthetic.resource_identity` in Tempo, Prometheus, and Loki and verify `service.name`, `service.version`, and `deployment.environment.name`. Also confirm the environment's normal authenticated health check still succeeds. If a signal is missing, check the two service states, private endpoint and security-group rules, token parameter type, and service logs; logs must not include token values.
