# 部署到 AWS（CloudFormation）

语言：[English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

> 本译文以[英文原文](README.md)为准；同步修订版本 `045796b0c7bbdd21520ccce1c7972495aab929f8`，同步日期 `2026-10-22`。

`cloudformation.yaml` 会创建一个 ECR 存储库、一个 ECS Fargate 服务（单个任务）以及一个面向公众的 Application Load Balancer。数据集存放在任务的临时磁盘上，任务重启时会丢失；这与应用采用尽力而为且会过期的数据集机制一致。不要将 `DesiredCount` 提高到 1 以上：每个数据集都是本地 DuckDB 文件。

需要已配置凭据的 AWS CLI 和 Docker。请选择具有两个公有子网的 VPC（默认 VPC 即可）。

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

可选参数：`PublicDemoMode=true`、`DatasetTtlHours`、`CertificateArn`（启用 HTTPS 并将 HTTP 重定向）。没有证书时站点使用普通 HTTP，因此上传的销售数据会以未加密方式传输；实际使用时请配置证书。发布新镜像时，请推送镜像并运行 `aws ecs update-service --force-new-deployment`。使用 `aws cloudformation delete-stack` 删除堆栈；请先清空 ECR 存储库。


## Docker Compose 部署

部署 Compose 覆盖配置会通过 Caddy 运行带有不可变 digest 的应用镜像。请在运行时提供完整镜像引用、公共主机名、环境和版本。开发环境还需要包含用户名和密码哈希的 Caddy basic-auth 块；请在运行时生成哈希并注入该块，不要将其提交到仓库。生产环境应留空该块并启用公开演示模式。

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

生产环境请提供 `CADDY_AUTH_BLOCK=''` 和 `PUBLIC_DEMO_MODE=true`，并设置 `OSA_ENVIRONMENT=production`。密码哈希是运行时输入；不要将凭据或哈希写入 Compose 文件、shell 历史记录或 CI 日志。
