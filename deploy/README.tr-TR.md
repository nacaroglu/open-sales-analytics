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
