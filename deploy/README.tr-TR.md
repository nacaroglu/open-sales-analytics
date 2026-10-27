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

Yerel ve kendin barındırdığın çalıştırmalar `PUBLIC_DEMO_MODE=false` varsayılanını kullanır ve CSV yüklemeyi sürdürür. Geliştirme ortamında `PUBLIC_DEMO_MODE=false` olmalı ve Caddy yapılandırması `basic_auth` içermelidir; üretimde `PUBLIC_DEMO_MODE=true` olmalı ve kimlik doğrulama bloğu boş kalmalıdır.
