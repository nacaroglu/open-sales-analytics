# AWS へのデプロイ（CloudFormation）

言語：[English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

> この翻訳は[英語の原文](README.md)を正とします。同期リビジョン `045796b0c7bbdd21520ccce1c7972495aab929f8`、同期日 `2026-10-22`。

`cloudformation.yaml` は、ECR リポジトリ、ECS Fargate サービス（1 タスク）、公開 Application Load Balancer を作成します。データセットはタスクの一時ディスクに置かれ、タスクの再起動時に失われます。これは、有効期限付きデータセットをベストエフォートで扱うアプリの方針に一致します。`DesiredCount` を 1 より大きくしないでください。各データセットはローカルの DuckDB ファイルです。

認証情報を設定した AWS CLI と Docker が必要です。2 つのパブリックサブネットを持つ VPC を選んでください（デフォルト VPC で構いません）。

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

任意のパラメーター：`PublicDemoMode=true`、`DatasetTtlHours`、`CertificateArn`（HTTPS を有効にし、HTTP をリダイレクト）。証明書がなければサイトは平文 HTTP となり、アップロードした販売データは暗号化されずに転送されます。実運用では設定してください。新しいイメージを配布するには、プッシュ後に `aws ecs update-service --force-new-deployment` を実行します。`aws cloudformation delete-stack` でスタックを削除できますが、先に ECR リポジトリを空にしてください。
