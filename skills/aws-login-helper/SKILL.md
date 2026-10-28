---
name: aws-login-helper
description: AWS CLIの既存プロファイルを使ってログイン失効を確認し、必要な場合だけ再認証してAWS MCPを起動する。日本語で案内する。SSOへの切り替えや認証方式の変更は行わない。
---

# AWSログイン補助

日本語で目的と変更範囲を説明する。AWSアカウントや認証情報を要求しない。プロファイル名、利用リージョン、OS、利用エージェントだけを確認する。

## 既存設定を優先

- AWS CLIのバージョンと選択したプロファイルの存在を確認する。設定ファイル全体や認証キャッシュを出力しない。
- IAM Identity CenterのSSOプロファイルなら既存の `aws sso login` を使う。このヘルパーを適用しない。
- 静的キー・credential_process・ロール引き受けなど別方式なら、勝手に `aws login` へ移行しない。
- 初回ログインと「以後、失効時にブラウザーを開く」動作について承認を得る。以後の承認済み範囲で毎回確認を繰り返さない。
- AWSの読み書き権限、課金、MFAはこの仕組みでは変更しない。

## 初回導入と問題の切り分け

初回導入または前提条件の検査に失敗したときは [onboarding.md](references/onboarding.md) を読む。
本ヘルパーはlogin_sessionがある既存のaws loginプロファイル用で、初期化は行わない。
全モードでCLIバージョンとプロファイル互換性を認証前に検査する。
CI/CDや別の認証方式へ適用しない。

## 同梱ヘルパー

[aws_mcp_login.py](scripts/aws_mcp_login.py) はPython 3.11以上、AWS CLI v2.32以上、MCP起動時はuvxを必要とする。実行前にコードを読む。CLIが見つからない場合は公式手順で導入し、既存インストールを削除しない。

利用者が指定した非秘密の値を渡す。以下の `example-dev` は説明用プロファイル名であり、自動作成しない。

```sh
python3 scripts/aws_mcp_login.py --profile example-dev --region ap-northeast-1 --check
python3 scripts/aws_mcp_login.py --profile example-dev --region ap-northeast-1 --login-only
```

実行パスはこのスキル内のスクリプト実体から解決する。Windowsでは実際のPython実行ファイルを使う。

- `--check`: 認証確認のみ。認証情報・アカウントID・ARNを出力しない。
- `--login-only`: 端末内でブラウザー認証を行う。秘密情報を会話へ転記しない。
- オプションなし: 有効ならMCPへ接続。失効なら再認証して接続する。
- ネットワーク障害や分類できないエラーでは自動ログインせず停止する。
- macOSのGUI起動ではTerminalを開く。Windows/LinuxのGUI起動では端末からの再認証を案内する。ヘッドレス認証は対象外。
- 同一プロファイルの同時起動をロックする。待機は原則3分。ブラウザー認証が長引いたら認証後にMCPを再接続する。
- ローカルにはロックファイルだけを作成する。認証情報はAWS CLI自身のキャッシュで管理される。

## 接続への組み込み

利用エージェントのMCP設定で、既存 `aws-mcp` の起動コマンドを「検出したPythonの絶対パス」、引数を「ヘルパーの絶対パス、--profile、選択値、--region、選択値」にする。対象以外の設定は保持する。既存の独自引数・複数アカウント設定がある場合は、単一プロファイルのこのヘルパーへ置換してよいか確認する。

初期化待機はCodexでは `startup_timeout_sec = 240`、Kiroでは現行仕様を確認して `timeout = 240000`。Claude Codeでは現行公式仕様の `MCP_TIMEOUT` を確認して起動環境へ設定する。タイムアウトを伸ばしても認証は省略できない。

tools/listまで成功した場合のみ「接続確認済み」と報告する。設定保存、認証成功、MCP起動、各アプリ内での利用を区別する。

参照: [AWS login](https://docs.aws.amazon.com/cli/latest/reference/login/)、[AWS MCP Proxy](https://github.com/aws/mcp-proxy-for-aws)。
