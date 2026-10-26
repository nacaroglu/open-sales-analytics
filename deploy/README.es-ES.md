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


## Pila foundation compartida

La plantilla independiente `deploy/cloudformation/osa-foundation.yaml` crea la VPC y las subredes compartidas, un repositorio ECR con etiquetas inmutables y análisis al publicar, el proveedor OIDC de GitHub Actions, el rol para compilar y publicar imágenes y el rol de ejecución de la pila foundation. No crea grupos de seguridad ni reglas de entrada. Las tablas de rutas privadas no tienen una ruta directa a la puerta de enlace de Internet.

### Parámetros y exportaciones

Elija AZ distintas para `AvailabilityZone1` y `AvailabilityZone2`. `VpcCidr`, los dos valores `PublicSubnet*Cidr` y los dos `PrivateSubnet*Cidr` definen rangos de red sin solapamiento; los valores predeterminados son `10.40.0.0/16` y cuatro subredes `/20`. Configure `GitHubOwner` y `GitHubRepository`; `GitHubMainBranch` tiene el valor predeterminado `main` y el subject OIDC se limita a esa rama exacta. `RepositoryName` tiene el valor predeterminado `open-sales-analytics`.

Despliegue con el nombre `osa-foundation` para obtener exportaciones estables calificadas por la pila: `osa-foundation-VpcId`, `osa-foundation-PublicSubnetAz1Id`, `osa-foundation-PublicSubnetAz2Id`, `osa-foundation-PrivateSubnetAz1Id`, `osa-foundation-PrivateSubnetAz2Id`, `osa-foundation-PublicSubnetIds`, `osa-foundation-PrivateSubnetIds`, `osa-foundation-RepositoryArn`, `osa-foundation-RepositoryUri`, `osa-foundation-OidcProviderArn`, `osa-foundation-BuildRoleArn`, `osa-foundation-FoundationExecutionRoleArn`, `osa-foundation-StackName` y `osa-foundation-Region`. En plantillas posteriores use `Fn::ImportValue`; para las listas de subredes separadas por comas, use `Fn::Split`.

La confianza de GitHub exige el subject exacto owner/repository/branch y la audiencia `sts.amazonaws.com`; no crea credenciales de larga duración. Consulte la [guía de GitHub sobre OIDC en AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

### Crear y validar

La creación de roles IAM con nombre requiere `CAPABILITY_NAMED_IAM`. Como la plantilla crea el rol `FoundationExecutionRoleArn`, la primera creación de la pila usa las credenciales de quien la solicita; no se puede pasar el rol con `--role-arn` antes de que exista. En una actualización posterior de esta misma pila, obtenga la salida `FoundationExecutionRoleArn` y pásela con `--role-arn`; quien llama necesita el permiso `iam:PassRole` para ese rol. CloudFormation lo asocia a las operaciones futuras de la pila. Consulte la documentación de AWS para [CreateStack](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateStack.html) y [UpdateStack](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html).

En el primer despliegue, omita `--role-arn` porque el rol aún no existe. Para un cambio posterior en la misma pila foundation, obtenga `FoundationExecutionRoleArn` y páselo al comando de despliegue habitual junto con el cambio de plantilla o parámetros:
```sh
REGION=eu-central-1; STACK=osa-foundation
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file deploy/cloudformation/osa-foundation.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides AvailabilityZone1=eu-central-1a AvailabilityZone2=eu-central-1b \
    GitHubOwner=OWNER GitHubRepository=open-sales-analytics
```

Valide localmente con el binario AWS `cfn-validate` firmado y fijado, además de las comprobaciones estáticas del repositorio:
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

El validador incluye esquemas y reglas; la validación no necesita credenciales de AWS ni conexión de red. CI verifica el SHA-256 y la firma separada del binario y no despliega esta plantilla. Consulte la [guía de validación de AWS CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html) y las [instrucciones de AWS para verificar la firma](https://github.com/aws-cloudformation/cloudformation-validate/blob/main/INSTALLATION.md).

### Eliminar y limpiar

Elimine las pilas dependientes que importen exportaciones antes de borrar `osa-foundation`; CloudFormation impide borrar una exportación que otra pila siga importando. Después ejecute `aws cloudformation delete-stack`. Elimine explícitamente las imágenes ECR antes de limpiar. Los límites de ciclo de vida y el vaciado al eliminar corresponden al issue #236. Revise los parámetros, las capacidades IAM y el conjunto de cambios de AWS antes de desplegar; la validación offline no confirma la disponibilidad de AZ o CIDR en la región. Consulte la [documentación de recursos de CloudFormation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html).
