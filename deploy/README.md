# Deploy to AWS (CloudFormation)

Languages: [English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

`cloudformation.yaml` creates an ECR repository, an ECS Fargate service (one task) and a public Application Load
Balancer. Datasets live on the task's ephemeral disk and are lost when the task restarts; that matches the app's
best-effort, expiring datasets. Do not raise `DesiredCount` above 1: each dataset is a local DuckDB file.

Needs the AWS CLI with credentials, and Docker. Pick a VPC with two public subnets (the default VPC works).

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

Optional parameters: `PublicDemoMode=true`, `DatasetTtlHours`, `CertificateArn` (enables HTTPS and redirects HTTP).
Without a certificate the site is plain HTTP, so uploaded sales data travels unencrypted; set one for real use.
To ship a new image, push it and run `aws ecs update-service --force-new-deployment`.
The legacy stack's former cleanup instruction to run `aws cloudformation delete-stack` and empty ECR manually does not apply to the shared foundation repository. Do not manually empty or delete that repository. Any foundation repository deletion must happen only through the guarded teardown process in #271, followed by removal verification in #272. Because EmptyOnDelete is enabled, that teardown force-deletes all remaining images, including images not yet expired.

## Docker Compose deployment

The deployment Compose override runs the application image by immutable digest behind Caddy. Provide the complete
image reference, public hostname, environment, and release version at runtime. Development also requires a Caddy
basic-auth block containing a username and a password hash; generate the hash at runtime and inject the block without
committing it. Production leaves that block empty and enables the public demo mode.

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

For production, set `OSA_ENVIRONMENT=production`, `PUBLIC_DEMO_MODE=true`, and `CADDY_AUTH_BLOCK=''`.
The password hash is runtime input; do not put credentials or hashes in Compose files, shell history, or CI logs.
The Caddy entrypoint validates this environment/mode/auth combination before starting its listener: development requires
`PUBLIC_DEMO_MODE=false` and a non-empty block containing a `basic_auth` directive; production requires
`PUBLIC_DEMO_MODE=true` and an explicitly empty block. Missing development auth, an empty development block, or a
production auth block stops Caddy before it binds public ports. The EC2 bootstrap contains only an empty auth placeholder;
the later #242 SSM integration supplies the development value at runtime. The backend independently rejects uploads in
public demo mode, so bypassing Caddy or the UI does not enable file uploads. Local and self-hosted runs default to
`PUBLIC_DEMO_MODE=false` and retain CSV uploads.


## Shared foundation stack

The separate `deploy/cloudformation/osa-foundation.yaml` template creates the shared VPC and subnets, immutable scan-on-push ECR repository, GitHub Actions OIDC provider, image build/push role, and foundation execution role. It creates no security groups or ingress rules. Private route tables have no direct internet-gateway route.

### Parameters and exports

Set `AvailabilityZone1` and `AvailabilityZone2` to distinct AZs. `VpcCidr`, the two `PublicSubnet*Cidr` values, and the two `PrivateSubnet*Cidr` values define non-overlapping network ranges; defaults are `10.40.0.0/16` and four `/20` subnets. Set `GitHubOwner` and `GitHubRepository`; `GitHubMainBranch` defaults to `main` and the OIDC subject matches that exact branch. `RepositoryName` defaults to `open-sales-analytics`.

Deploy as `osa-foundation` to use stable stack-qualified exports: `osa-foundation-VpcId`, `osa-foundation-PublicSubnetAz1Id`, `osa-foundation-PublicSubnetAz2Id`, `osa-foundation-PrivateSubnetAz1Id`, `osa-foundation-PrivateSubnetAz2Id`, `osa-foundation-PublicSubnetIds`, `osa-foundation-PrivateSubnetIds`, `osa-foundation-RepositoryArn`, `osa-foundation-RepositoryUri`, `osa-foundation-OidcProviderArn`, `osa-foundation-BuildRoleArn`, `osa-foundation-FoundationExecutionRoleArn`, osa-foundation-DevDeployRoleArn, osa-foundation-DevVerificationRoleArn, osa-foundation-ProductionPromotionRoleArn, osa-foundation-DevApplicationExecutionRoleArn, osa-foundation-ProdApplicationExecutionRoleArn, osa-foundation-ObservabilityExecutionRoleArn, osa-foundation-Ec2InstanceRoleArn, `osa-foundation-ObservabilityEc2InstanceRoleName`, `osa-foundation-StackName`, and `osa-foundation-Region`. Import values in later templates with `Fn::ImportValue`; use `Fn::Split` for the comma-separated subnet lists.

The existing BuildRole trusts only the configured GitHub repository's main-branch subject and pushes to this stack's Repository ARN. DevDeployRole has the exact owner/repository/main-branch subject and sts.amazonaws.com audience; its only CloudFormation mutation is UpdateStack on stack osa-dev, it reads only that stack, requires the stack's DevApplicationExecutionRole for updates, and may pass only DevApplicationExecutionRole to CloudFormation through iam:PassRole. DevVerificationRole trusts the same main-branch subject but grants only DescribeStacks on osa-dev and exact SecureString retrieval/decryption for the smoke credential. ProductionPromotionRole trusts only the configured repository's environment:production subject and the same audience; it targets only osa-prod and may pass only ProdApplicationExecutionRole to CloudFormation through iam:PassRole. Keep the production GitHub environment protected.

DevApplicationExecutionRole, ProdApplicationExecutionRole, and ObservabilityExecutionRole trust only cloudformation.amazonaws.com. They restrict mutable EC2 resources by OSAStack tags for osa-dev, osa-prod, and osa-observability respectively; the dev role can pass only DevCaddyAuthEc2InstanceRole, the prod role can pass only Ec2InstanceRole, and the observability role can pass only ObservabilityEc2InstanceRole to ec2.amazonaws.com. DevApplicationExecutionRole and ProdApplicationExecutionRole can access only their exact release-image metadata parameter; they have no wildcard SSM resource access and cannot read the secret paths reserved for #242. ObservabilityExecutionRole retains only its separate observability-path parameter read. Ec2InstanceRole trusts only ec2.amazonaws.com, reads images only from Repository, and uses a custom minimal Session Manager policy without broad Parameter Store reads. ObservabilityEc2InstanceRole is a dedicated observability runtime role; it can read only `/osa/observability/grafana/admin-password` as SecureString and decrypt only through regional Systems Manager with the exact parameter encryption context and `alias/aws/ssm` condition. Neither application EC2 role can read this Grafana secret. FoundationExecutionRole remains the foundation-only service role and retains its repository-scoped ECR lifecycle permissions from #236.

The Resource: * exceptions are limited to ECR authorization-token retrieval in BuildRole and Ec2InstanceRole; DescribeVpcState and ListFoundationProviders in FoundationExecutionRole; and DescribeEc2State, RunTaggedOsaDevInstances, CreateTagsForOsaDevInstances, RunTaggedOsaProdInstances, CreateTagsForOsaProdInstances, RunTaggedOsaObservabilityInstances, and CreateTagsForOsaObservabilityInstances in the workload execution roles. EC2 RunInstances and tag-on-create exceptions require the exact environment OSAStack request tag and the foundation VPC; all other mutable EC2 permissions use environment resource tags or explicit resource ARNs. AWS documents the required RunInstances resource set and tag-on-create pattern at https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ExamplePolicies_EC2.html and EC2 action/resource scope at https://docs.aws.amazon.com/service-authorization/latest/reference/list_ec2.html. See AWS guidance for CloudFormation service roles and stack scoping, PassRole restrictions, and Systems Manager instance permissions: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-iam-servicerole.html, https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/control-access-with-iam.html, https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_passrole.html, and https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-instance-permissions.html.

The GitHub trust requires the exact owner/repository/branch subject and `sts.amazonaws.com` audience; it grants no long-lived credentials. See [GitHub's AWS OIDC guide](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

### Create and validate

Creating named IAM roles requires `CAPABILITY_NAMED_IAM`. The first stack creation must use the caller's credentials: the stack creates `FoundationExecutionRoleArn` itself, so it cannot be passed as `--role-arn` before it exists. On a later update to this same stack, retrieve `FoundationExecutionRoleArn` and pass it with `--role-arn`; the caller must have `iam:PassRole` permission. CloudFormation then associates that role for future stack operations. See the [AWS CreateStack documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateStack.html) and [UpdateStack documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html).

```sh
REGION=eu-central-1; STACK=osa-foundation
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file deploy/cloudformation/osa-foundation.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides AvailabilityZone1=eu-central-1a AvailabilityZone2=eu-central-1b \
    GitHubOwner=OWNER GitHubRepository=open-sales-analytics
```

The initial deployment omits `--role-arn` because the role does not exist yet. For a later update of the foundation stack, retrieve `FoundationExecutionRoleArn` and pass it to the normal deployment command, together with the template or parameter change being applied:

```sh
EXECUTION_ROLE_ARN=$(aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \\
  --query "Stacks[0].Outputs[?OutputKey=='FoundationExecutionRoleArn'].OutputValue" --output text)
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \\
  --template-file deploy/cloudformation/osa-foundation.yaml \\
  --capabilities CAPABILITY_NAMED_IAM --role-arn "$EXECUTION_ROLE_ARN" \\
  --parameter-overrides AvailabilityZone1=eu-central-1a AvailabilityZone2=eu-central-1b \\
    GitHubOwner=OWNER GitHubRepository=open-sales-analytics
```

Validate locally with the signed, pinned AWS `cfn-validate` binary and the repository's static assertions:

```sh
cfn-validate --strict deploy/cloudformation/osa-foundation.yaml
python3 scripts/validate_foundation_template.py
```

The validator bundles schemas and rules, so the validation itself needs no AWS credentials or network. CI verifies the binary's SHA-256 and detached signature before running it; CI never deploys this template. See the [AWS CloudFormation validation guide](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html) and [AWS validator signature instructions](https://github.com/aws-cloudformation/cloudformation-validate/blob/main/INSTALLATION.md).

### Delete and cleanup

Delete downstream stacks before `osa-foundation`; CloudFormation prevents deleting exports still imported by another stack. Foundation repository deletion must happen only through the guarded teardown process in #271, followed by removal verification in #272. Do not manually empty the ECR repository or delete the foundation stack as a repository cleanup shortcut. The repository's EmptyOnDelete setting force-deletes all remaining images, including images not yet expired. Review parameters, IAM capabilities, and the AWS change set before any deployment; offline validation does not confirm regional AZ or CIDR availability. See [CloudFormation resource documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html).


The foundation reuses the VPC, subnets, routes, and stack-qualified exports in deploy/cloudformation/osa-foundation.yaml; it adds no duplicate network resources. The public route table is associated only with PublicSubnetAz1 and PublicSubnetAz2, and its 0.0.0.0/0 route targets the attached InternetGateway. Each private subnet is associated with its own private route table. Those tables retain only the VPC-local route: they have no default, NAT, instance, peering, Internet Gateway, or other unreviewed egress route. All four subnets keep MapPublicIpOnLaunch: false. The public route defines an internet-gateway path; the route alone does not create a workload or expose a listener. AWS guidance: https://docs.aws.amazon.com/vpc/latest/userguide/subnet-route-tables.html and https://docs.aws.amazon.com/us_en/AWSEC2/latest/UserGuide/working-with-ip-addresses.html.

The foundation template declares no security groups, network ACLs, ingress rules, or public listeners. Public SSH (TCP 22) and public OTLP (TCP 4317 and TCP 4318) are prohibited; this stack introduces no other public listener. Security-group rules belong to the workload stack that owns the associated resources. AWS guidance: https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html.

Any workload egress needed for image pulls, certificate acquisition, runtime operation, or AWS management must be explicit, limited to that purpose, and implemented by the owning workload stack. App/Caddy ingress is HTTP/HTTPS only, with no SSH, and belongs to issue #240. Observability/Grafana ingress belongs to issue #263. Private authenticated Collector OTLP access on ports 4317 and 4318 is allowed only from the dev/prod application security groups and belongs to issue #264. Those workload-specific groups and rules are not created by the foundation.

PR/CI validation creates no AWS resources and leaves no stack, VPC, route, security group, local generated file, or credential to clean up. The offline checks make no AWS API calls and do not deploy the template.

The ECR repository uses immutable release tags, so a release tag cannot be overwritten; each build should use a new unique tag. Its single lifecycle rule applies to any image, tagged or untagged: when more than ten images remain, it expires the oldest and retains the ten most recently pushed images. ECR evaluates lifecycle rules and normally expires images that meet the criteria within 24 hours, so retention is bounded by policy but cleanup is not immediate. AWS references: https://docs.aws.amazon.com/AmazonECR/latest/userguide/lifecycle_policy_parameters.html and https://docs.aws.amazon.com/AmazonECR/latest/userguide/LifecyclePolicies.html.

The repository's EmptyOnDelete setting is destructive. When CloudFormation deletes or replaces Repository, it force-deletes remaining image contents, including images not yet expired under the lifecycle policy. Ordinary PR/CI validation and deployment workflows do not delete the repository. Final deletion occurs only through the guarded teardown process in #271, followed by removal verification in #272. See https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ecr-repository.html.

Validation does not create AWS stacks or resources and leaves no generated repository artifact or credential in the checkout or CI artifacts.

The shared `deploy/cloudformation/osa-application.yaml` is deployed twice as `osa-dev` and `osa-prod`. Both stacks use the same template and parameter names; select `Environment=development` or `Environment=production`, and supply `ImageDigest`, `ReleaseVersion`, `AmiId`, `InstanceType`, and `PublicHostname` at deploy time. `AmiId` must be an Amazon Linux 2023 image ID in the target region, and its architecture must match the selected instance type and image. `ImageDigest` is exactly 64 lowercase SHA-256 hexadecimal characters; `ReleaseVersion` is readable runtime metadata. `PublicHostname` is a dotted DNS name with valid labels. None of these inputs is an AWS credential or secret.

CI derives each readable release version once from the UTC build time and the source commit: `YYYYMMDD-HHMMSS-<first seven lowercase commit-SHA characters>`. `backend/app/release_version.py` validates the full Git object ID and prints the version used by the image build; later delivery jobs consume that same output rather than generating a second version.

After all required CI jobs succeed for a push to `main`, the workflow publishes the exact validated image artifact to the immutable ECR repository using the release version as its tag. It then resolves and validates the ECR SHA-256 digest and exposes the repository URI, version, digest, and `repository@sha256:digest` reference as job outputs for the development deploy job. A collision with an existing immutable version fails the publish job; CI never overwrites that tag. Pull-request CI remains read-only and does not request AWS credentials.

If none of the three variables below is set, the publication job and the development deploy and verification jobs that depend on it are skipped. If any one is set, the job runs and fails when another is missing, so a partial configuration is never ignored.

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

Each stack creates exactly one EC2 instance in `osa-foundation`'s first public subnet, disables automatic public-IP assignment, and attaches one stack-owned Elastic IP. Production uses `Ec2InstanceRole`; development uses `DevCaddyAuthEc2InstanceRole`. Both roles use a custom minimal Session Manager policy with only `ssm:UpdateInstanceInformation` and `ssmmessages:CreateControlChannel`, `ssmmessages:CreateDataChannel`, `ssmmessages:OpenControlChannel`, and `ssmmessages:OpenDataChannel`, without `AmazonSSMManagedInstanceCore` and its wildcard Parameter Store reads. Development additionally has `ssm:GetParameter` for only `arn:aws:ssm:<region>:<account>:parameter/osa/dev/caddy/auth` and `kms:Decrypt` only through regional Systems Manager, with the exact `PARAMETER_ARN` encryption context and `alias/aws/ssm` resource-alias condition. Production has no permission to retrieve or decrypt the auth parameter. The dev and prod CloudFormation execution roles may pass only their respective instance role to EC2. The instance has no SSH key pair. Administer it through Systems Manager Session Manager. AWS documents the minimal instance-profile policy for Session Manager at https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-create-iam-instance-profile.html.

The app security group allows only public IPv4 TCP 80 and 443. Port 80 supports ACME validation and redirects to HTTPS; TCP 443 serves the application through Caddy. Egress allows TCP 443 to public IPv4 for ECR API and S3 image-layer downloads, Systems Manager, certificate acquisition, and required runtime endpoints, plus TCP 4318 only to the imported private Collector security group for OTLP/HTTP. Security groups cannot filter AmazonProvidedDNS, so no broad DNS rule is declared. There is no public SSH or OTLP ingress, IPv6 rule, or Route 53 resource in this stack.

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


### Development deployment verification

After `deploy-dev` succeeds on `main`, `verify-dev` assumes the read-only `DevVerificationRole` exported as `osa-foundation-DevVerificationRoleArn` (configure repository variable `OSA_DEV_VERIFICATION_ROLE_ARN`). It reads only the `osa-dev` stack outputs and `/osa/dev/caddy/smoke-credential`. The credential is a SecureString in `username:password` format. Add a dedicated smoke user to `/osa/dev/caddy/auth` while preserving its existing human-user entries; use the procedure below. Keep both values out of GitHub secrets/variables, source control, command output, and logs.

The verifier checks the stack digest and release version against the published artifact, polls HTTPS `/health/ready` with normal TLS certificate and hostname validation for up to five minutes, creates the bundled sample through Basic Auth, checks its USD metadata and exact analytics, then deletes it using its dataset Bearer token. It masks the credential before further output and publishes only hostname, release version, digest, readiness, and cleanup status in the workflow summary. Any mismatch, timeout, or failed cleanup fails the job.

### Manual production promotion

Configure the repository-level variables `OSA_AWS_REGION`, `OSA_ECR_REPOSITORY_URI`, `OSA_PRODUCTION_SOURCE_READ_ROLE_ARN`, `OSA_PROD_PROMOTION_ROLE_ARN`, `OSA_PROD_EXECUTION_ROLE_ARN`, `OSA_AMI_ID`, `OSA_INSTANCE_TYPE`, and `OSA_PROD_HOSTNAME`. The source-read role is exported as `osa-foundation-ProductionSourceReadRoleArn`; the production promotion and execution roles use the exports documented above.

Create the GitHub repository Environment named `production`, enable required reviewers, and prevent self-review where the repository plan supports it. Add the intended operators as reviewers. The `promote-production.yml` workflow is started with Actions → Promote development release to production → Run workflow, using the `main` branch. It reads and validates the current dev digest/version with the read-only source role. The promotion job pauses for the `production` Environment approval before it obtains the production role credentials. After approval, it rereads dev and prod metadata, records the old prod release, and updates `osa-prod` to the current dev digest and version without building or retagging. It then checks production readiness and exercises sample creation, representative analytics, and cleanup over HTTPS. If the stack update, readiness check, or sample journey fails, the workflow restores the recorded digest/version and verifies readiness and release metadata again. The promotion job remains failed after any failed production check, even when rollback succeeds. The summary reports the promoted and previous releases, verification result, and rollback result; `Rollback: FAILED` means an operator must investigate the production stack and endpoint before another promotion. Open the run summary to inspect these results.

The production promotion role's OIDC trust uses the exact subject `repo:<owner>/<repository>:environment:production` and audience `sts.amazonaws.com`. The source-read role has two exact subjects: the repository's configured main branch for preflight and the protected `production` Environment for a fresh source read after approval. It has only `cloudformation:DescribeStacks` on `osa-dev`. The production promotion role can update and read only `osa-prod` and pass only `ProdApplicationExecutionRole` to CloudFormation. Do not configure AWS access keys.

### Observability stack

Deploy `osa-observability` after `osa-foundation` and before `osa-dev` or `osa-prod`. The foundation template exports `ObservabilityExecutionRoleArn` for the CloudFormation service role and `ObservabilityEc2InstanceRoleName` for the runtime instance profile. Use the execution role with `--role-arn`; it can pass only the dedicated observability EC2 role. The observability stack exports `CollectorSecurityGroupId`. Each application stack imports that ID and owns its OTLP ingress rule, with its local application security group as the source. This dependency means delete the dev and prod application stacks before deleting observability, then delete foundation.

Before creating the stack, provision the fixed admin secret as an SSM `SecureString` using the AWS managed `alias/aws/ssm` key. Enter the password silently; do not print it or place it in shell history, user data, a template, or CI output:

```sh
read -rsp 'Grafana admin password: ' grafana_password; printf '\n'
aws ssm put-parameter --name /osa/observability/grafana/admin-password \
  --type SecureString --value "$grafana_password" --overwrite >/dev/null
unset grafana_password
```

Deploy using the pinned config commit and region-specific Amazon Linux 2023 AMI:

```sh
aws cloudformation deploy --region "$REGION" --stack-name osa-observability \
  --template-file deploy/cloudformation/osa-observability.yaml \
  --capabilities CAPABILITY_IAM \
  --role-arn "$OSA_OBSERVABILITY_EXECUTION_ROLE_ARN" \
  --parameter-overrides AmiId="$OSA_AMI_ID" InstanceType=t3.small \
    GrafanaHostname="$OSA_GRAFANA_HOSTNAME" \
    GrafanaAdminParameterName=/osa/observability/grafana/admin-password \
    ObservabilityConfigRevision="$OSA_CONFIG_REVISION"
aws cloudformation describe-stacks --region "$REGION" --stack-name osa-observability \
  --query 'Stacks[0].Outputs'
```

The outputs are the public IP, HTTPS Grafana URL, private Collector OTLP/HTTP endpoint, and exported `CollectorSecurityGroupId` and `CollectorPrivateEndpoint`. The endpoint export is consumed by #264 for application-side OTLP configuration. The instance signals CloudFormation only after it verifies that the fixed SSM parameter exists, is a `SecureString`, and can be decrypted by the dedicated runtime role. A failed check fails stack creation; user data logs only a generic corrective message. After stack creation, point an A record for `GrafanaHostname` at `GrafanaPublicIp`; Caddy retries certificate acquisition until public DNS resolves. Grafana's `GF_SERVER_ROOT_URL` is derived from `GrafanaHostname` and set to the public HTTPS URL for dashboard links. Ports 80 and 443 are public for ACME and HTTPS. This stack has no OTLP or SSH ingress; #264 adds private OTLP ingress in each app stack, sourced from that app's security group. Grafana has anonymous access disabled. The runtime role retrieves the password at service startup and places it only in a mode-restricted `/run` secret file owned by the Grafana container UID; the value is not stored on EBS or emitted to logs. Root and telemetry EBS volumes are encrypted and deleted with the stack. Deleting this stack removes telemetry data.

Offline schema and security checks run in the `cloudformation-foundation` CI job. They do not deploy AWS resources. The #264 app-side Collector endpoint/token configuration is a separate change.

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

### Authenticated private OTLP ingestion

The app reads the private `CollectorPrivateEndpoint` export and sends OTLP/HTTP on TCP 4318. Its security group permits this traffic only to `CollectorSecurityGroupId`, and the Collector accepts app traffic through the matching security-group ingress. The endpoint is private; no public OTLP listener is created. The dev and prod tokens are environment-specific SSM `SecureString` parameters at `/osa/dev/observability/otlp-token` and `/osa/prod/observability/otlp-token`.

To rotate a token, set `OTLP_TOKEN_PARAMETER` to the matching dev or prod parameter path. Generate a fresh URL-safe token into a mode-restricted temporary file with `umask 077; TOKEN_FILE=$(mktemp); openssl rand -base64 32 | tr '+/' '-_' | tr -d '=' > "$TOKEN_FILE"`, then update the parameter with `aws ssm put-parameter --name "$OTLP_TOKEN_PARAMETER" --type SecureString --value "file://$TOKEN_FILE" --overwrite >/dev/null`. Do not print the token or use `--with-decryption` to inspect it. Through Session Manager, restart `osa-observability.service` on the Collector instance and `osa-compose.service` on the matching application instance; confirm both are active. Each service reloads its token from SSM at startup. Preflight checks verify that the environment parameter exists and has type `SecureString` without decrypting or exposing its value.

To verify authenticated private ingestion, connect to the matching application instance through Session Manager and run `docker compose --env-file /opt/osa/.env -f /opt/osa/compose.yaml exec -T app env PYTHONPATH=/app/backend OSA_ENVIRONMENT=development python -m app.telemetry_test_signal`; set `OSA_ENVIRONMENT=production` for prod. This emits a synthetic trace, metric, and log using the app's configured private endpoint and token file, without displaying the token. Confirm the command reports a successful flush, then use Grafana Explore to find `osa.synthetic.resource_identity` in Tempo, Prometheus, and Loki and verify `service.name`, `service.version`, and `deployment.environment.name`. Also confirm the environment's normal authenticated health check still succeeds. If a signal is missing, check the two service states, private endpoint and security-group rules, token parameter type, and service logs; logs must not include token values.

### Guarded Phase 4 teardown

The teardown deletes the four CloudFormation stacks in this order, waiting for each deletion to finish before starting the next:

1. `osa-dev`
2. `osa-prod`
3. `osa-observability`
4. `osa-foundation`

Run `.github/workflows/teardown-phase4.yml` manually from `main`; it has no push, pull-request or schedule trigger. CloudFormation owns resource deletion, including ECR empty-on-delete behavior. Do not manually delete resources or ECR images.

**Pre-teardown checklist.** Confirm every item before choosing `execute`:

- Retain anything you still need. Deleting `osa-foundation` force-deletes the ECR repository and its images, and the observability data volume is deleted with no snapshot or backup. Export evidence first (#270).
- Nothing outside the four stacks imports their exports. The preflight refuses to continue otherwise.
- All four stacks are in a stable state (not `*_IN_PROGRESS` and not a failed state that needs manual repair).
- The `osa-teardown` environment has required reviewers (see below) and the repository variables `OSA_AWS_REGION`, `OSA_TEARDOWN_AWS_ACCOUNT_ID`, `OSA_TEARDOWN_PREFLIGHT_ROLE_ARN` and `OSA_TEARDOWN_ROLE_ARN` are set. The preflight role must only inspect identity, target stack states, exports and importers. The delete role must have the same read access and be allowed to delete only the four target stacks.
- You are on `main` and the person approving is aware of the account and region being targeted.

**Approval configuration.** Repository changes cannot configure GitHub environment settings, so an administrator must create the `osa-teardown` environment, add required reviewers and restrict deployment branches to `main`. Verify the protection with the GitHub API (requires `gh` authenticated with repository administration read access):

```sh
gh api repos/nacaroglu/open-sales-analytics/environments/osa-teardown \
  | python3 scripts/verify_phase4_environment.py
```

The checker fails if the API response has no non-empty `required_reviewers` rule.

**Dry run.** The dry run lists the exact targets and order, makes no AWS calls and deletes nothing:

```sh
gh workflow run teardown-phase4.yml --ref main -f mode=dry-run
```

**Execution.** Execution requires the exact confirmation value `DELETE-PHASE4-OSA-RESOURCES`. The workflow runs a read-only preflight (account, region, stable stack states, outside importers), then waits at the protected `osa-teardown` environment so a reviewer can inspect the preflight result before approving deletion:

```sh
gh workflow run teardown-phase4.yml --ref main -f mode=execute -f confirmation=DELETE-PHASE4-OSA-RESOURCES
```

Approve the pending deployment in the workflow run. An absent stack is skipped. The workflow prints each stack outcome and a safe failure stage in `GITHUB_STEP_SUMMARY`, with no account IDs, ARNs or raw AWS responses.

**Recovery after a failure.** A failed delete or wait stops the run: later stacks are not touched, and the run is never retried automatically. Read the summary table to see which stacks are deleted, absent or not attempted, then use the failure stage:

- `workflow_setup`, `confirmation` or `region_configuration`: nothing was changed. The workflow or script stopped before AWS was used, for example because the confirmation value was not exact or a repository variable is missing. Rerun with the exact confirmation value and the repository variables set, including the correct `OSA_AWS_REGION`.
- `aws_identity`, `account_configuration`, `aws_client`, `aws_query`, `aws_response` or `aws_pagination`: the preflight could not verify the account or read AWS. Nothing was deleted. Check the role trust, the account ID variable and the region, then rerun.
- `stack_query`, `stack_state`, `export_query`, `import_query` or `outside_importer`: the preflight refused. Wait for in-progress stacks to settle, repair a failed stack, or remove the outside importer, then rerun.
- `delete_request` or `delete_wait`: CloudFormation failed to start or finish a stack deletion. Open the stack's events in the CloudFormation console to find the blocking resource, fix it, wait until the stack is stable (for example `DELETE_FAILED` after you remove the blocker), then rerun the workflow. Already deleted stacks are skipped.

If the summary shows `unknown`, treat it as a failed run of undetermined cause: read the workflow log, confirm the state of all four stacks in the CloudFormation console, and rerun only when they are stable.

Do not skip stacks or delete resources by hand to work around a failure. Final absence verification is tracked by #272.
