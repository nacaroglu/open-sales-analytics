# Despliegue en AWS (CloudFormation)

[English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

> Traducción del documento [en inglés](README.md), que es la fuente de referencia. Revisión de sincronización: `045796b0c7bbdd21520ccce1c7972495aab929f8`, con fecha `2026-10-22`.

`cloudformation.yaml` crea un repositorio de ECR, un servicio de ECS Fargate (una tarea) y un Application Load
Balancer público. Los conjuntos de datos residen en el disco efímero de la tarea y se pierden cuando esta se reinicia;
esto concuerda con los conjuntos de datos temporales y de persistencia no garantizada de la aplicación. No aumente
`DesiredCount` por encima de 1: cada conjunto de datos es un archivo DuckDB local.

Se necesitan la AWS CLI con credenciales y Docker. Elija una VPC con dos subredes públicas (la VPC predeterminada sirve).

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

Parámetros opcionales: `PublicDemoMode=true`, `DatasetTtlHours`, `CertificateArn` (habilita HTTPS y redirige HTTP).
Sin un certificado, el sitio usa HTTP sin cifrar, por lo que los datos de ventas cargados viajan sin cifrado; configure
uno para un uso real. Para publicar una imagen nueva, envíela al repositorio y ejecute
`aws ecs update-service --force-new-deployment`. Elimine la pila con `aws cloudformation delete-stack`; primero vacíe
el repositorio de ECR.


## Despliegue con Docker Compose

La configuración de despliegue de Compose ejecuta la imagen de la aplicación con un digest inmutable detrás de Caddy. Proporciona en tiempo de ejecución la referencia completa de la imagen, el nombre de host público, el entorno y la versión. El entorno de desarrollo también requiere un bloque basic-auth de Caddy con un usuario y un hash de contraseña; genera el hash en tiempo de ejecución e inyecta el bloque sin confirmarlo en el repositorio. En producción, deja el bloque vacío y activa el modo de demostración pública.

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

Para la configuración de producción, proporciona `CADDY_AUTH_BLOCK=''` y `PUBLIC_DEMO_MODE=true`, y establece `OSA_ENVIRONMENT=production`. El hash de contraseña es una entrada de ejecución; no guardes credenciales ni hashes en archivos Compose, en el historial del shell ni en los registros de CI.
