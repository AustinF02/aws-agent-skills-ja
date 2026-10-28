---
name: aws-mcp-setup
description: AWS公式MCPを既存の名前付きプロファイルでCodex・Kiro・Claude Codeへ接続し、認証とツール検出を確認する。日本語で案内し、AWSリソースやIAM権限は変更しない。
---

# AWS MCPの設定と接続

利用エージェント、OS、プロファイル名、ワークロードのリージョン、既存の認証方式を確認する。秘密情報を求めない。初回のブラウザー認証が必要なら説明して承認を得る。

## 最小の変更

- 既存の `aws-mcp` があれば設定・動作を先に確認する。別名で重複追加しない。
- `uvx` とAWS CLIを検出する。GUIのPATHと端末のPATHが異なる場合は、検出した実行ファイルの絶対パスを使う。
- AWS MCP接続先は現行公式資料で確認する。初期の例は `https://aws-mcp.us-east-1.api.aws/mcp`。接続先のリージョンとワークロードのリージョンを混同しない。
- 公式proxyの現行CLI配布は `mcp-proxy-for-aws-cli@latest`。外部コードの取得になることを説明する。Agent Toolkitが生成した既存の起動引数は、必要性を確認せず置き換えない。
- 名前付きプロファイルは `AWS_MCP_PROXY_PROFILES` で指定する。 `AWS_REGION` と `AWS_DEFAULT_REGION` は利用者のワークロードリージョンにする。固定のアカウント・プロファイル・利用者のパスを再配布しない。

Codexの設定例（説明用の非秘密値。実際の選択値で生成する）:
```toml
[mcp_servers.aws-mcp]
command = "uvx"
args = ["mcp-proxy-for-aws-cli@latest", "https://aws-mcp.us-east-1.api.aws/mcp"]
startup_timeout_sec = 60

[mcp_servers.aws-mcp.env]
AWS_MCP_PROXY_PROFILES = "example-dev"
AWS_REGION = "ap-northeast-1"
AWS_DEFAULT_REGION = "ap-northeast-1"
```

Kiroは `mcpServers.aws-mcp` のcommand/args/envへ同じ値を設定する。Claude Codeは公式CLIのstdio登録を使用する。既存設定を一括上書きせず、保存後に構文と対象外エントリーの一致を確認する。

## 再認証の自動化を希望した場合だけ

ログイン時にブラウザーを開くことを説明してから、利用可能な `aws-login-helper` スキルを読む。未導入なら [ログイン補助スキル](https://github.com/AustinF02/aws-agent-skills-ja/tree/main/skills/aws-login-helper) の追加を案内する。単一プロファイル用であり、既存の複数プロファイル構成を無断で置換しない。

## 検証と失敗時

1. 選択プロファイルでSTSを確認する。ID・ARNを出力せず、成功/失敗だけ記録する。
2. MCP初期化とtools/listを確認する。アカウントを変更するツールは呼ばない。
3. 設定保存・認証・MCP初期化・実アプリでの動作を分けて日本語で報告する。
4. JSON-RPCの `Invalid request parameters` だけで原因を決めつけない。秘密情報を除いたログで、失効・リージョン不足・プロファイル違い・接続障害を切り分ける。
5. 権限不足でもAdministratorAccessやワイルドカード許可を自動付与しない。2回の修正で解決しなければ事実と次の確認事項を報告する。

参照: [AWS MCP Proxy](https://github.com/aws/mcp-proxy-for-aws)、[Codex MCP](https://developers.openai.com/codex/mcp)、[Kiro MCP](https://kiro.dev/docs/mcp/configuration/)、[Claude Code MCP](https://code.claude.com/docs/en/mcp)。
