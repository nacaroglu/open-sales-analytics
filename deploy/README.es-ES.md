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

The shared `deploy/cloudformation/osa-application.yaml` is deployed twice as `osa-dev` and `osa-prod`. Both stacks use the same template and parameter names; select `Environment=development` or `Environment=production`, and supply `ImageDigest`, `ReleaseVersion`, `AmiId`, `InstanceType`, and `PublicHostname` at deploy time. `AmiId` must be an Amazon Linux 2023 image ID in the target region, and its architecture must match the selected instance type and image. `ImageDigest` is exactly 64 lowercase SHA-256 hexadecimal characters; `ReleaseVersion` is readable runtime metadata. `PublicHostname` is a dotted DNS name with valid labels. None of these inputs is an AWS credential or secret.

Each stack creates exactly one EC2 instance in `osa-foundation`'s first public subnet, disables automatic public-IP assignment, and attaches one stack-owned Elastic IP. Production uses `Ec2InstanceRole`; development uses `DevCaddyAuthEc2InstanceRole`. Both roles use a custom minimal Session Manager policy with only `ssm:UpdateInstanceInformation` and `ssmmessages:CreateControlChannel`, `ssmmessages:CreateDataChannel`, `ssmmessages:OpenControlChannel`, and `ssmmessages:OpenDataChannel`, without `AmazonSSMManagedInstanceCore` and its wildcard Parameter Store reads. Development additionally has `ssm:GetParameter` for only `arn:aws:ssm:<region>:<account>:parameter/osa/dev/caddy/auth` and `kms:Decrypt` only through regional Systems Manager, with the exact `PARAMETER_ARN` encryption context and `alias/aws/ssm` resource-alias condition. Production has no permission to retrieve or decrypt the auth parameter. The dev and prod CloudFormation execution roles may pass only their respective instance role to EC2. The instance has no SSH key pair. Administer it through Systems Manager Session Manager. AWS documents the minimal instance-profile policy for Session Manager at https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-create-iam-instance-profile.html.

The app security group allows only public IPv4 TCP 80 and 443. Port 80 supports ACME validation and redirects to HTTPS; TCP 443 serves the application through Caddy. The only declared egress is TCP 443 to public IPv4 for ECR API and S3 image-layer downloads, Systems Manager, certificate acquisition, and required runtime endpoints. Security groups cannot filter AmazonProvidedDNS, so no broad DNS rule is declared. There is no public SSH or OTLP ingress, IPv6 rule, Route 53 resource, or private Collector route in this stack.

Before Caddy can obtain a public certificate, create an A record for the supplied hostname in your DNS provider or zone and point it to the stack's `PublicIp` output. The `PublicEndpoint` output is the corresponding HTTPS URL. Caddy and the application use version/digest-pinned images, wait for the application readiness check, and restart through Compose/systemd. The application image is pulled by the instance profile through the ECR credential helper with its disk cache disabled; no ECR password is written to user data or a file. The stack does not build images. Temporary DuckDB files remain on the instance/container filesystem. No application-data EBS volume, snapshot, backup, or durable mount is created; deleting the app stack removes its instance, root disk, profile, security group, and Elastic IP. Delete both application stacks before deleting `osa-foundation`.

The outputs include the instance ID, Elastic IP, hostname, HTTPS endpoint, image digest/reference, release version, and release metadata parameter name. The SSM release parameter is a non-secret `String`, not a `SecureString`; it records the immutable image reference only. Development uses `/osa/dev/release/image`, and production uses `/osa/prod/release/image`. Secret provisioning and runtime secret injection belong to #242.


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

Las ejecuciones locales y autoalojadas usan `PUBLIC_DEMO_MODE=false` de forma predeterminada y mantienen las cargas CSV. En desarrollo, `PUBLIC_DEMO_MODE=false` y la configuración de Caddy debe incluir `basic_auth`; en producción, `PUBLIC_DEMO_MODE=true` y el bloque de autenticación debe estar vacío.
