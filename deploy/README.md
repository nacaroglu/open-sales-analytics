# Deploy to AWS (CloudFormation)

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
Delete the stack with `aws cloudformation delete-stack`; empty the ECR repository first.
