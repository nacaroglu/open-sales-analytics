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


## Shared foundation stack

The separate `deploy/cloudformation/osa-foundation.yaml` template creates the shared VPC and subnets, immutable scan-on-push ECR repository, GitHub Actions OIDC provider, image build/push role, and foundation execution role. It creates no security groups or ingress rules. Private route tables have no direct internet-gateway route.

### Parameters and exports

Set `AvailabilityZone1` and `AvailabilityZone2` to distinct AZs. `VpcCidr`, the two `PublicSubnet*Cidr` values, and the two `PrivateSubnet*Cidr` values define non-overlapping network ranges; defaults are `10.40.0.0/16` and four `/20` subnets. Set `GitHubOwner` and `GitHubRepository`; `GitHubMainBranch` defaults to `main` and the OIDC subject matches that exact branch. `RepositoryName` defaults to `open-sales-analytics`.

Deploy as `osa-foundation` to use stable stack-qualified exports: `osa-foundation-VpcId`, `osa-foundation-PublicSubnetAz1Id`, `osa-foundation-PublicSubnetAz2Id`, `osa-foundation-PrivateSubnetAz1Id`, `osa-foundation-PrivateSubnetAz2Id`, `osa-foundation-PublicSubnetIds`, `osa-foundation-PrivateSubnetIds`, `osa-foundation-RepositoryArn`, `osa-foundation-RepositoryUri`, `osa-foundation-OidcProviderArn`, `osa-foundation-BuildRoleArn`, `osa-foundation-FoundationExecutionRoleArn`, osa-foundation-DevDeployRoleArn, osa-foundation-ProductionPromotionRoleArn, osa-foundation-DevApplicationExecutionRoleArn, osa-foundation-ProdApplicationExecutionRoleArn, osa-foundation-ObservabilityExecutionRoleArn, osa-foundation-Ec2InstanceRoleArn, `osa-foundation-StackName`, and `osa-foundation-Region`. Import values in later templates with `Fn::ImportValue`; use `Fn::Split` for the comma-separated subnet lists.

The existing BuildRole trusts only the configured GitHub repository's main-branch subject and pushes to this stack's Repository ARN. DevDeployRole has the same exact owner/repository/main-branch subject and sts.amazonaws.com audience; its CloudFormation permissions target only stack osa-dev, require that stack's DevApplicationExecutionRole and may pass only DevApplicationExecutionRole to CloudFormation through iam:PassRole. ProductionPromotionRole trusts only the configured repository's environment:production subject and the same audience; it targets only osa-prod and may pass only ProdApplicationExecutionRole to CloudFormation through iam:PassRole. Keep the production GitHub environment protected.

DevApplicationExecutionRole, ProdApplicationExecutionRole, and ObservabilityExecutionRole trust only cloudformation.amazonaws.com. They restrict mutable EC2 resources by OSAStack tags for osa-dev, osa-prod, and osa-observability respectively; each can pass only Ec2InstanceRole to ec2.amazonaws.com. Their SSM parameter reads are limited to the matching osa/dev, osa/prod, or osa/observability path. Ec2InstanceRole trusts only ec2.amazonaws.com, reads images only from Repository, and attaches AWS's AmazonSSMManagedInstanceCore policy for Session Manager and Run Command. It does not create an instance profile; that attachment belongs to #240. FoundationExecutionRole remains the foundation-only service role and retains its repository-scoped ECR lifecycle permissions from #236.

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

The single shared application template at deploy/cloudformation/osa-application.yaml is intended for later separate stacks named osa-dev and osa-prod. Pass Environment=development or Environment=production, a 64-character lowercase SHA-256 ImageDigest, and a readable non-empty ReleaseVersion; development writes the immutable repository-URI-at-digest value to /osa/dev/release/image, while production uses /osa/prod/release/image. Both values are non-secret SSM String release metadata only; they are not SecureString credentials and do not configure the instance runtime. The template imports only osa-foundation-RepositoryUri and outputs the environment, immutable image reference, release version, and parameter name. It creates no workload, network, ingress, durable-data, or backup resources; later runtime work belongs to #240 and secret injection to #242. The resource uses CloudFormation-managed tags and its app stack manages its lifecycle. AWS documents CloudFormation template resources at https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/resources-section-structure.html and the SSM String parameter resource and tag behavior at https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ssm-parameter.html.
