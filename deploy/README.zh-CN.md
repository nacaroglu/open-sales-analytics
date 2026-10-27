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


## 共享 foundation 堆栈

独立模板 `deploy/cloudformation/osa-foundation.yaml` 会创建共享 VPC 和子网、标签不可变且推送时扫描的 ECR 存储库、GitHub Actions OIDC 提供方、镜像构建/推送角色以及 foundation 堆栈执行角色。模板不会创建安全组或入站规则。私有路由表没有直达互联网网关的路由。

### 参数和导出

为 `AvailabilityZone1` 和 `AvailabilityZone2` 选择不同的 AZ。`VpcCidr`、两个 `PublicSubnet*Cidr` 和两个 `PrivateSubnet*Cidr` 用于定义互不重叠的网络范围；默认值为 `10.40.0.0/16` 和四个 `/20` 子网。设置 `GitHubOwner` 和 `GitHubRepository`；`GitHubMainBranch` 默认为 `main`，OIDC subject 仅匹配该分支。`RepositoryName` 默认为 `open-sales-analytics`。

以 `osa-foundation` 为堆栈名部署，即可获得稳定且带堆栈名前缀的导出值：`osa-foundation-VpcId`、`osa-foundation-PublicSubnetAz1Id`、`osa-foundation-PublicSubnetAz2Id`、`osa-foundation-PrivateSubnetAz1Id`、`osa-foundation-PrivateSubnetAz2Id`、`osa-foundation-PublicSubnetIds`、`osa-foundation-PrivateSubnetIds`、`osa-foundation-RepositoryArn`、`osa-foundation-RepositoryUri`、`osa-foundation-OidcProviderArn`、`osa-foundation-BuildRoleArn`、`osa-foundation-FoundationExecutionRoleArn`、`osa-foundation-StackName` 和 `osa-foundation-Region`。后续模板使用 `Fn::ImportValue` 导入；逗号分隔的子网列表使用 `Fn::Split` 转换。

GitHub 信任策略要求精确的 owner/repository/branch subject 和 `sts.amazonaws.com` audience；不会创建长期凭据。请参阅 [GitHub 的 AWS OIDC 指南](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)。

### 创建和验证

创建具名 IAM 角色需要 `CAPABILITY_NAMED_IAM`。由于模板本身会创建 `FoundationExecutionRoleArn` 角色，首次创建堆栈时使用调用方凭据；角色尚不存在，因此不能通过 `--role-arn` 传入。在此堆栈后续更新时，获取 `FoundationExecutionRoleArn` 输出并使用 `--role-arn` 指定；调用方必须具有该角色的 `iam:PassRole` 权限。之后 CloudFormation 会将该角色关联到后续堆栈操作。请参阅 AWS [CreateStack 文档](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateStack.html)和 [UpdateStack 文档](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html)。

首次部署时请省略 `--role-arn`，因为该角色尚未创建。对此 foundation 堆栈进行后续更改时，获取 `FoundationExecutionRoleArn`，并将其与要应用的模板或参数更改一起传给常规部署命令：
```sh
REGION=eu-central-1; STACK=osa-foundation
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file deploy/cloudformation/osa-foundation.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides AvailabilityZone1=eu-central-1a AvailabilityZone2=eu-central-1b \
    GitHubOwner=OWNER GitHubRepository=open-sales-analytics
```

使用带签名且固定版本的 AWS `cfn-validate` 二进制文件及仓库静态检查进行本地验证：
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

验证器内置了 CloudFormation 架构和规则，因此验证本身不需要 AWS 凭据或网络连接。CI 会核验二进制文件的 SHA-256 和独立签名；不会部署此模板。请参阅 [AWS CloudFormation 验证指南](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html)和 [AWS 验证器签名说明](https://github.com/aws-cloudformation/cloudformation-validate/blob/main/INSTALLATION.md)。

### 删除和清理

删除 `osa-foundation` 前，先删除所有导入其导出值的下游堆栈；只要仍有堆栈导入，CloudFormation 就不允许删除导出值。然后运行 `aws cloudformation delete-stack`。清理前请显式删除 ECR 镜像。生命周期上限和删除时清空由 issue #236 负责。部署前请检查参数、IAM 能力和 AWS 变更集；离线验证无法确认目标区域中的 AZ 或 CIDR 是否可用。请参阅 [CloudFormation 资源文档](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html)。

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
