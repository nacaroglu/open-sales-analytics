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
