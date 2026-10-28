# AWS'ye Dağıtım (CloudFormation)

[English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

> Bu çevirinin doğruluk kaynağı [İngilizce belgedir](README.md). Eşitleme revizyonu: `045796b0c7bbdd21520ccce1c7972495aab929f8` (2026-10-22).

`cloudformation.yaml` bir ECR deposu, bir ECS Fargate hizmeti (tek görev) ve herkese açık bir Application Load
Balancer oluşturur. Veri kümeleri görevin geçici diskinde bulunur ve görev yeniden başladığında kaybolur; bu,
uygulamanın en iyi çabaya dayalı ve süresi dolan veri kümeleriyle uyumludur. `DesiredCount` değerini 1'in üzerine
çıkarmayın: her veri kümesi yerel bir DuckDB dosyasıdır.

Kimlik bilgileriyle yapılandırılmış AWS CLI ve Docker gereklidir. İki herkese açık alt ağa sahip bir VPC seçin
(varsayılan VPC uygundur).

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

İsteğe bağlı parametreler: `PublicDemoMode=true`, `DatasetTtlHours`, `CertificateArn` (HTTPS'yi etkinleştirir ve HTTP'yi
yönlendirir). Sertifika olmadan site düz HTTP kullanır; dolayısıyla yüklenen satış verileri şifrelenmeden aktarılır.
Gerçek kullanım için bir sertifika ayarlayın. Yeni bir imaj yayımlamak için onu gönderin ve
`aws ecs update-service --force-new-deployment` çalıştırın. Yığını `aws cloudformation delete-stack` ile silin; önce
ECR deposunu boşaltın.


## Docker Compose dağıtımı

Dağıtım Compose geçersiz kılması, uygulama imajını değişmez bir digest ile Caddy arkasında çalıştırır. Tam imaj referansını, genel hostname değerini, ortamı ve sürümü çalışma anında sağlayın. Geliştirme ortamı ayrıca kullanıcı adı ve parola özeti içeren bir Caddy basic-auth bloğu gerektirir; özeti çalışma anında oluşturup bloğu enjekte edin, depoya kaydetmeyin. Üretimde bu blok boş bırakılır ve genel demo modu etkinleştirilir.

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

Üretim ayarları için `CADDY_AUTH_BLOCK=''` değerini ve `PUBLIC_DEMO_MODE=true` değerini sağlayıp `OSA_ENVIRONMENT=production` ayarlayın. Parola özeti çalışma zamanı girdisidir; kimlik bilgilerini veya özetleri Compose dosyalarına, kabuk geçmişine ya da CI günlüklerine koymayın.


## Paylaşılan foundation yığını

Ayrı `deploy/cloudformation/osa-foundation.yaml` şablonu ortak VPC ve alt ağları, değiştirilemez ve gönderimde taranan ECR deposunu, GitHub Actions OIDC sağlayıcısını, görüntü oluşturma/gönderme rolünü ve foundation yürütme rolünü oluşturur. Güvenlik grubu veya giriş kuralı oluşturmaz. Özel yönlendirme tablolarında internet ağ geçidine doğrudan rota bulunmaz.

### Parametreler ve dışa aktarımlar

`AvailabilityZone1` ve `AvailabilityZone2` için farklı AZ değerleri seçin. `VpcCidr`, iki `PublicSubnet*Cidr` ve iki `PrivateSubnet*Cidr` çakışmayan ağ aralıklarını tanımlar; varsayılanlar `10.40.0.0/16` ve dört `/20` alt ağıdır. `GitHubOwner` ile `GitHubRepository` değerlerini ayarlayın; `GitHubMainBranch` varsayılan olarak `main` olur ve OIDC konusu tam bu dala bağlıdır. `RepositoryName` varsayılanı `open-sales-analytics` değeridir.

`osa-foundation` adıyla dağıtım, aşağıdaki kararlı ve yığın adıyla nitelenmiş dışa aktarımları sağlar: `osa-foundation-VpcId`, `osa-foundation-PublicSubnetAz1Id`, `osa-foundation-PublicSubnetAz2Id`, `osa-foundation-PrivateSubnetAz1Id`, `osa-foundation-PrivateSubnetAz2Id`, `osa-foundation-PublicSubnetIds`, `osa-foundation-PrivateSubnetIds`, `osa-foundation-RepositoryArn`, `osa-foundation-RepositoryUri`, `osa-foundation-OidcProviderArn`, `osa-foundation-BuildRoleArn`, `osa-foundation-FoundationExecutionRoleArn`, `osa-foundation-StackName` ve `osa-foundation-Region`. Sonraki şablonlarda `Fn::ImportValue` kullanın; virgülle ayrılmış alt ağ listeleri için `Fn::Split` uygulayın.

GitHub güveni tam depo sahibi/depo/dal konusunu ve `sts.amazonaws.com` kitlesini gerektirir; uzun ömürlü kimlik bilgisi verilmez. [GitHub AWS OIDC kılavuzuna](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws) bakın.

### Oluşturma ve doğrulama

Adlandırılmış IAM rolleri oluşturmak için `CAPABILITY_NAMED_IAM` gerekir. Şablon `FoundationExecutionRoleArn` rolünü kendisi oluşturduğu için ilk yığın oluşturma çağıranın kimlik bilgileriyle yapılır; rol mevcut olmadan `--role-arn` ile verilemez. Aynı yığının sonraki bir güncellemesinde `FoundationExecutionRoleArn` çıktısını alın ve `--role-arn` ile belirtin; çağıranın bu rol için `iam:PassRole` izni olmalıdır. CloudFormation bu rolü sonraki yığın işlemleri için ilişkilendirir. [AWS CreateStack belgelerine](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateStack.html) ve [UpdateStack belgelerine](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html) bakın.

İlk dağıtımda rol henüz mevcut olmadığından `--role-arn` kullanmayın. Aynı foundation yığınında daha sonraki bir değişiklik için `FoundationExecutionRoleArn` çıktısını alıp uygulanacak şablon veya parametre değişikliğiyle birlikte normal dağıtım komutuna verin:
```sh
REGION=eu-central-1; STACK=osa-foundation
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file deploy/cloudformation/osa-foundation.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides AvailabilityZone1=eu-central-1a AvailabilityZone2=eu-central-1b \
    GitHubOwner=OWNER GitHubRepository=open-sales-analytics
```

İmzalı ve sürümü sabitlenmiş AWS `cfn-validate` ikilisiyle ve depodaki statik kontrollerle yerel doğrulama yapın:
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

Doğrulayıcı şema ve kuralları içerir; doğrulama sırasında AWS kimlik bilgisi veya ağ bağlantısı gerekmez. CI ikilinin SHA-256 değerini ve ayrık imzasını doğrular; bu şablonu dağıtmaz. [AWS CloudFormation doğrulama kılavuzuna](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html) ve [AWS doğrulayıcı imza yönergelerine](https://github.com/aws-cloudformation/cloudformation-validate/blob/main/INSTALLATION.md) bakın.

### Silme ve temizleme

Dışa aktarımlarını kullanan tüm alt yığınları `osa-foundation` yığınından önce silin; başka bir yığın dışa aktarımı içe aktarırken CloudFormation bunun silinmesine izin vermez. Ardından `aws cloudformation delete-stack` çalıştırın. Temizlemeden önce ECR görüntülerini açıkça kaldırın. Sınırlandırılmış yaşam döngüsü ve silmede boşaltma #236 kapsamındadır. Dağıtım öncesinde parametreleri, IAM yeteneklerini ve AWS değişiklik kümesini inceleyin; çevrimdışı doğrulama bölgedeki AZ veya CIDR kullanılabilirliğini teyit etmez. [CloudFormation kaynak belgelerine](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html) bakın.

The shared `deploy/cloudformation/osa-application.yaml` is deployed twice as `osa-dev` and `osa-prod`. Both stacks use the same template and parameter names; select `Environment=development` or `Environment=production`, and supply `ImageDigest`, `ReleaseVersion`, `AmiId`, `InstanceType`, and `PublicHostname` at deploy time. `AmiId` must be an Amazon Linux 2023 image ID in the target region, and its architecture must match the selected instance type and image. `ImageDigest` is exactly 64 lowercase SHA-256 hexadecimal characters; `ReleaseVersion` is readable runtime metadata. `PublicHostname` is a dotted DNS name with valid labels. None of these inputs is an AWS credential or secret.

Each stack creates exactly one EC2 instance in `osa-foundation`'s first public subnet, disables automatic public-IP assignment, and attaches one stack-owned Elastic IP. Production uses `Ec2InstanceRole`; development uses `DevCaddyAuthEc2InstanceRole`. Both roles use a custom minimal Session Manager policy with only `ssm:UpdateInstanceInformation` and `ssmmessages:CreateControlChannel`, `ssmmessages:CreateDataChannel`, `ssmmessages:OpenControlChannel`, and `ssmmessages:OpenDataChannel`, without `AmazonSSMManagedInstanceCore` and its wildcard Parameter Store reads. Development additionally has `ssm:GetParameter` for only `arn:aws:ssm:<region>:<account>:parameter/osa/dev/caddy/auth` and `kms:Decrypt` only through regional Systems Manager, with the exact `PARAMETER_ARN` encryption context and `alias/aws/ssm` resource-alias condition. Production has no permission to retrieve or decrypt the auth parameter. The dev and prod CloudFormation execution roles may pass only their respective instance role to EC2. The instance has no SSH key pair. Administer it through Systems Manager Session Manager. AWS documents the minimal instance-profile policy for Session Manager at https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-create-iam-instance-profile.html.

The app security group allows only public IPv4 TCP 80 and 443. Port 80 supports ACME validation and redirects to HTTPS; TCP 443 serves the application through Caddy. The only declared egress is TCP 443 to public IPv4 for ECR API and S3 image-layer downloads, Systems Manager, certificate acquisition, and required runtime endpoints. Security groups cannot filter AmazonProvidedDNS, so no broad DNS rule is declared. There is no public SSH or OTLP ingress, IPv6 rule, Route 53 resource, or private Collector route in this stack.

Before Caddy can obtain a public certificate, create an A record for the supplied hostname in your DNS provider or zone and point it to the stack's `PublicIp` output. The `PublicEndpoint` output is the corresponding HTTPS URL. Caddy and the application use version/digest-pinned images, wait for the application readiness check, and restart through Compose/systemd. The application image is pulled by the instance profile through the ECR credential helper with its disk cache disabled; no ECR password is written to user data or a file. The stack does not build images. Temporary DuckDB files remain on the instance/container filesystem. No application-data EBS volume, snapshot, backup, or durable mount is created; deleting the app stack removes its instance, root disk, profile, security group, and Elastic IP. Delete both application stacks before deleting `osa-foundation`.

The outputs include the instance ID, Elastic IP, hostname, HTTPS endpoint, image digest/reference, release version, and release metadata parameter name. The SSM release parameter is a non-secret `String`, not a `SecureString`; it records the immutable image reference only. Development uses `/osa/dev/release/image`, and production uses `/osa/prod/release/image`. Secret provisioning and runtime secret injection belong to #242.


CI derives each readable release version once from the UTC build time and the source commit: `YYYYMMDD-HHMMSS-<first seven lowercase commit-SHA characters>`. `backend/app/release_version.py` validates the full Git object ID and prints the version used by the image build; later delivery jobs consume that same output rather than generating a second version.

After all required CI jobs succeed for a push to `main`, the workflow publishes the exact validated image artifact to the immutable ECR repository using the release version as its tag. It then resolves and validates the ECR SHA-256 digest and exposes the repository URI, version, digest, and `repository@sha256:digest` reference as job outputs for the development deploy job. A collision with an existing immutable version fails the publish job; CI never overwrites that tag. Pull-request CI remains read-only and does not request AWS credentials.

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

Yerel ve kendin barındırdığın çalıştırmalar `PUBLIC_DEMO_MODE=false` varsayılanını kullanır ve CSV yüklemeyi sürdürür. Geliştirme ortamında `PUBLIC_DEMO_MODE=false` olmalı ve Caddy yapılandırması `basic_auth` içermelidir; üretimde `PUBLIC_DEMO_MODE=true` olmalı ve kimlik doğrulama bloğu boş kalmalıdır.


### Geliştirme dağıtımının doğrulanması

After `deploy-dev` succeeds on `main`, `verify-dev` assumes the read-only `DevVerificationRole` exported as `osa-foundation-DevVerificationRoleArn` (configure repository variable `OSA_DEV_VERIFICATION_ROLE_ARN`). It reads only the `osa-dev` stack outputs and `/osa/dev/caddy/smoke-credential`. The credential is a SecureString in `username:password` format. Add a dedicated smoke user to `/osa/dev/caddy/auth` while preserving its existing human-user entries; use the procedure below. Keep both values out of GitHub secrets/variables, source control, command output, and logs.

The verifier checks the stack digest and release version against the published artifact, polls HTTPS `/health/ready` with normal TLS certificate and hostname validation for up to five minutes, creates the bundled sample through Basic Auth, checks its USD metadata and exact analytics, then deletes it using its dataset Bearer token. It masks the credential before further output. The verification job summary records environment, immutable image tag/version, digest, readiness, sample analytics, and temporary sample cleanup; it omits hostnames, account IDs, credentials, tokens, and raw command output. A failed verification summary names the failed stage and cleanup result. The deploy job also summarizes update success or failure; `CloudFormation rollback: NOT VERIFIED` means an operator should inspect the stack status. Any mismatch, timeout, or failed cleanup fails the job.

### Üretimin elle terfi ettirilmesi

Configure the repository-level variables `OSA_AWS_REGION`, `OSA_ECR_REPOSITORY_URI`, `OSA_PRODUCTION_SOURCE_READ_ROLE_ARN`, `OSA_PROD_PROMOTION_ROLE_ARN`, `OSA_PROD_EXECUTION_ROLE_ARN`, `OSA_AMI_ID`, `OSA_INSTANCE_TYPE`, and `OSA_PROD_HOSTNAME`. The source-read role is exported as `osa-foundation-ProductionSourceReadRoleArn`; the production promotion and execution roles use the exports documented above.

Create the GitHub repository Environment named `production`, enable required reviewers, and prevent self-review where the repository plan supports it. Add the intended operators as reviewers. The `promote-production.yml` workflow is started with Actions → Promote development release to production → Run workflow, using the `main` branch. It reads and validates the current dev digest/version with the read-only source role. The promotion job pauses for the `production` Environment approval before it obtains the production role credentials. After approval, it rereads dev and prod metadata, records the old prod release, and updates `osa-prod` to the current dev digest and version without building or retagging. Open the run summary to inspect source, target, and previous release metadata.

`Rollback: FAILED` means an operator must inspect production before another promotion.

The production promotion role's OIDC trust uses the exact subject `repo:<owner>/<repository>:environment:production` and audience `sts.amazonaws.com`. The source-read role has two exact subjects: the repository's configured main branch for preflight and the protected `production` Environment for a fresh source read after approval. It has only `cloudformation:DescribeStacks` on `osa-dev`. The production promotion role can update and read only `osa-prod` and pass only `ProdApplicationExecutionRole` to CloudFormation. Do not configure AWS access keys.

The Caddy Basic Auth exception applies only to `/api/datasets/` paths with a 22-character URL-safe dataset ID and a 43-character URL-safe Bearer header. FastAPI validates the token. Readiness, sample creation, and all other paths remain Basic Auth protected.

To add or rotate the dedicated smoke user without replacing the existing human user, run this in a private terminal with shell tracing disabled. It retrieves the existing auth block into a shell variable without printing it, appends one bcrypt entry, and writes both SecureStrings from mode-restricted temporary files. Choose a username not already in the block. The password is entered silently; use the same username and password for both parameters.

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

### Gözlemlenebilirlik yığını

`osa-observability` yığınını foundation'dan sonra ve uygulama yığınlarından önce dağıtın. Dev ve prod uygulama yığınları Collector güvenlik grubu kimliğini içe aktarır ve yalnızca kendi uygulama güvenlik gruplarından özel OTLP erişim kuralını yönetir. Silme sırasında önce uygulama yığınlarını, sonra observability yığınını, en son foundation'ı kaldırın. Collector özel uç noktası ve güvenlik grubu kimliği dışa aktarılır; OTLP kimlik doğrulama belirteçleri ortamlarına ait SSM `SecureString` parametrelerinde tutulur.
