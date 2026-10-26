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


## Docker Compose によるデプロイ

デプロイ用 Compose オーバーライドは、不変の digest を指定したアプリケーションイメージを Caddy の背後で実行します。完全なイメージ参照、公開ホスト名、環境、バージョンを実行時に指定してください。開発環境では、ユーザー名とパスワードハッシュを含む Caddy basic-auth ブロックも必要です。ハッシュを実行時に生成してブロックを注入し、リポジトリにはコミットしないでください。本番環境ではブロックを空にして、公開デモモードを有効にします。

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

本番設定では `CADDY_AUTH_BLOCK=''` と `PUBLIC_DEMO_MODE=true` を指定し、`OSA_ENVIRONMENT=production` に設定します。パスワードハッシュは実行時入力です。認証情報やハッシュを Compose ファイル、シェル履歴、CI ログに含めないでください。


## 共有 foundation スタック

独立した `deploy/cloudformation/osa-foundation.yaml` テンプレートは、共有 VPC とサブネット、タグが不変でプッシュ時にスキャンする ECR リポジトリ、GitHub Actions OIDC プロバイダー、イメージのビルド/プッシュ用ロール、foundation スタック実行ロールを作成します。セキュリティグループやインバウンドルールは作成しません。プライベートのルートテーブルにはインターネットゲートウェイへの直接ルートがありません。

### パラメーターとエクスポート

`AvailabilityZone1` と `AvailabilityZone2` には異なる AZ を指定します。`VpcCidr`、2 つの `PublicSubnet*Cidr` と 2 つの `PrivateSubnet*Cidr` で重複しないネットワーク範囲を指定します。デフォルトは `10.40.0.0/16` と 4 つの `/20` サブネットです。`GitHubOwner` と `GitHubRepository` を設定します。`GitHubMainBranch` のデフォルトは `main` で、OIDC subject はそのブランチだけに一致します。`RepositoryName` のデフォルトは `open-sales-analytics` です。

スタック名を `osa-foundation` にしてデプロイすると、スタック名を含む安定したエクスポートが作成されます: `osa-foundation-VpcId`、`osa-foundation-PublicSubnetAz1Id`、`osa-foundation-PublicSubnetAz2Id`、`osa-foundation-PrivateSubnetAz1Id`、`osa-foundation-PrivateSubnetAz2Id`、`osa-foundation-PublicSubnetIds`、`osa-foundation-PrivateSubnetIds`、`osa-foundation-RepositoryArn`、`osa-foundation-RepositoryUri`、`osa-foundation-OidcProviderArn`、`osa-foundation-BuildRoleArn`、`osa-foundation-FoundationExecutionRoleArn`、`osa-foundation-StackName`、`osa-foundation-Region`。後続テンプレートでは `Fn::ImportValue` で値を取り込み、カンマ区切りのサブネット一覧は `Fn::Split` でリストにします。

GitHub の信頼ポリシーは owner/repository/branch subject と `sts.amazonaws.com` audience の完全一致を要求し、長期認証情報は作成しません。[GitHub の AWS OIDC ガイド](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)を参照してください。

### 作成と検証

名前付き IAM ロールの作成には `CAPABILITY_NAMED_IAM` が必要です。このテンプレート自身が `FoundationExecutionRoleArn` ロールを作成するため、初回のスタック作成は呼び出し元の認証情報で行います。ロールの作成前に `--role-arn` で渡すことはできません。同じスタックを後で更新するときは、出力 `FoundationExecutionRoleArn` を取得して `--role-arn` に指定します。呼び出し元にはこのロールの `iam:PassRole` 権限が必要です。CloudFormation は以後のスタック操作にこのロールを関連付けます。AWS の [CreateStack ドキュメント](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_CreateStack.html)と [UpdateStack ドキュメント](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_UpdateStack.html)を参照してください。

初回デプロイではロールがまだないため `--role-arn` を省略します。同じ foundation スタックに後続の変更を行う際は、`FoundationExecutionRoleArn` を取得して、適用するテンプレートまたはパラメーターの変更とともに通常のデプロイコマンドに渡します:
```sh
REGION=eu-central-1; STACK=osa-foundation
aws cloudformation deploy --region "$REGION" --stack-name "$STACK" \
  --template-file deploy/cloudformation/osa-foundation.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides AvailabilityZone1=eu-central-1a AvailabilityZone2=eu-central-1b \
    GitHubOwner=OWNER GitHubRepository=open-sales-analytics
```

署名を検証した固定バージョンの AWS `cfn-validate` バイナリとリポジトリの静的チェックでローカル検証します:
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

検証ツールにはスキーマとルールが含まれるため、検証そのものに AWS 認証情報やネットワーク接続は不要です。CI はバイナリの SHA-256 と detached signature を検証し、テンプレートをデプロイしません。[AWS CloudFormation 検証ガイド](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html)と[AWS 検証ツールの署名手順](https://github.com/aws-cloudformation/cloudformation-validate/blob/main/INSTALLATION.md)を参照してください。

### 削除とクリーンアップ

`osa-foundation` を削除する前に、そのエクスポートをインポートしている下位スタックをすべて削除してください。他のスタックからインポート中のエクスポートは CloudFormation で削除できません。その後 `aws cloudformation delete-stack` を実行します。クリーンアップ前に ECR イメージを明示的に削除してください。ライフサイクル上限と削除時の空化は issue #236 の対象です。デプロイ前にパラメーター、IAM capabilities、AWS change set を確認してください。オフライン検証では対象リージョンの AZ や CIDR の利用可否は確認できません。[CloudFormation リソースドキュメント](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html)を参照してください。
