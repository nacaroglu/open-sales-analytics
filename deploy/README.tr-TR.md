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

Doğrulayıcı şema ve kuralları içerir; doğrulama sırasında AWS kimlik bilgisi veya ağ bağlantısı gerekmez. CI ikilinin SHA-256 değerini ve ayrık imzasını doğrular; bu şablonu dağıtmaz. [AWS CloudFormation doğrulama kılavuzuna](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html) ve [AWS doğrulayıcı imza yönergelerine](https://github.com/aws-cloudformation/cloudformation-validate/blob/main/INSTALLATION.md) bakın.

### Silme ve temizleme

Dışa aktarımlarını kullanan tüm alt yığınları `osa-foundation` yığınından önce silin; başka bir yığın dışa aktarımı içe aktarırken CloudFormation bunun silinmesine izin vermez. Ardından `aws cloudformation delete-stack` çalıştırın. Temizlemeden önce ECR görüntülerini açıkça kaldırın. Sınırlandırılmış yaşam döngüsü ve silmede boşaltma #236 kapsamındadır. Dağıtım öncesinde parametreleri, IAM yeteneklerini ve AWS değişiklik kümesini inceleyin; çevrimdışı doğrulama bölgedeki AZ veya CIDR kullanılabilirliğini teyit etmez. [CloudFormation kaynak belgelerine](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html) bakın.
