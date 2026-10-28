# 初回セットアップとトラブルシューティング

初回導入または前提条件の確認に失敗したときだけ読む。AWS操作の失敗だけを理由にログインしない。

## 初回導入

1. OS、対象プロファイル、リージョン、既存の認証方式を確認し、利用者のローカル端末で `aws --version` を実行する。Python 3.11以上、AWS CLI v2.32.0以上のv2系、MCP起動時はuvxが必要。不足時は[公式導入手順](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)を使い、インストールや認証方式の変更は承認範囲で行う。
2. IAM Identity Centerは `aws sso login` を維持する。静的キー、credential_process、ロール引き受けも保持し、それらのプロファイルへ本ヘルパーを登録しない。
3. コンソール認証を新たに使う場合は、ブラウザー・MFAの手順を説明して承認を得る。利用者が選んだ非秘密の値で、ローカル端末から `aws login --profile <PROFILE_NAME> --region <REGION>` を実行する。既存方式を残す場合は別の名前付きプロファイルを使い、defaultを無断で選択・上書きしない。
4. ヘルパーは空でない `login_session` が設定済みのプロファイルだけを受け付ける。別方式・混在設定と、共有credentialsファイルの同名プロファイル節は空でも拒否する。検査を通すために既存設定を削除・書き換えず、専用の互換プロファイルを選ぶ。
5. 対象プロファイルでヘルパーの `--check` を実行する。以後の失効時にブラウザーを開く承認を得てMCPへ組み込む。MCPのツール一覧を取得するまで接続成功と報告しない。

スクリプトは互換性の確認のため、共有credentialsファイルを含む設定を端末内で読み取る。内容は出力せず、認証キャッシュは読み取らない。前提条件の検査は `AWS_CONFIG_FILE` と `AWS_SHARED_CREDENTIALS_FILE` の指定先を使う。起動環境を揃える。

## 問題の切り分け

| 状況 | 対応 |
| --- | --- |
| CLI未導入・未対応・バージョン判定不能 | 公式手順で導入・更新する。推測でログインを開始しない |
| プロファイルなし・login_sessionなし | 承認済みの初回ログインを、ヘルパーの外で対象の名前付きプロファイルへ実施 |
| SSO・別方式・混在設定 | 既存方式を維持し、自動移行しない |
| サインイン自体の権限不足 | AWS Sign-Inの必要権限を確認し管理者へ相談。ポリシーを自動付与しない |
| ログイン後にAWSサービスがAccessDenied | 対象サービスのIAMを調査。再ログインやサインイン権限の追加で操作権限は増えない |
| 通信障害・未分類エラー | 接続と原因を調査し、セッション失効と断定しない |
| ブラウザーが使えない | 別途承認された手動手順なら `aws login --remote` を確認。本ヘルパーはヘッドレス・別端末認証を自動化しない |
| キャンセル・待機時間超過 | 端末で認証を完了してMCPを再接続 |

`SignInLocalDevelopmentAccess` はサインイン用トークン操作の権限で、業務サービスの操作権限ではない。実際のエラーと現行の公式ポリシーを確認する。CI/CDでは対話ログインを使わず、適切なロール・フェデレーションを使う。導入前に現行のパーティション・リージョン対応を確認する。

参照: [CLIコンソール認証](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)、[サインイン用ポリシー](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/SignInLocalDevelopmentAccess.html)、[設定ファイル](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)。
