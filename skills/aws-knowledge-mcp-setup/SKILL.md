---
name: aws-knowledge-mcp-setup
description: AWS Knowledge MCPの接続をCodex・Kiro・Claude Codeへ追加し、公式ドキュメント検索を日本語で確認する。AWSアカウントの操作やログインは対象外。
---

# AWS Knowledge MCPの接続

公式エンドポイントは `https://knowledge-mcp.global.api.aws`。AWS認証は不要で、レート制限がある。AWSリソースを操作するAWS MCPとは別物である。

1. 利用アプリと設定スコープを確認する。既存設定を読むが、無関係なトークンやヘッダーを出力しない。
2. 同名サーバーがあれば接続を先に確認する。動いていれば何も変更しない。異なる設定なら差分と理由を説明してから統合する。
3. 下記を完成ファイルとして上書きせず、対象エントリーだけ追加する。

CodexのTOML:
```toml
[mcp_servers.aws-knowledge-mcp-server]
url = "https://knowledge-mcp.global.api.aws"
```

KiroのJSON:
```json
{
  "mcpServers": {
    "aws-knowledge-mcp-server": {
      "url": "https://knowledge-mcp.global.api.aws",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Claude Codeは現行CLIのヘルプで構文を確認し、未登録時のみ実行:
```sh
claude mcp add --transport http --scope user aws-knowledge-mcp-server https://knowledge-mcp.global.api.aws
```

4. 再接続し、tools/listを実行する。実際に返されたツール名を使って、例えば「Lambdaの実行環境について公式資料を1件検索」を確認する。ツール名は固定しない。
5. 自動承認は既定で増やさない。必要なら利用者が指定した読み取りツールだけを対象にする。
6. 設定保存と検索成功を分けて日本語で報告する。認証を求められたらAWSキーを入力せず、接続先とクライアント仕様を見直す。

参照: [AWS公式Knowledge MCP](https://awslabs.github.io/mcp/servers/aws-knowledge-mcp-server)、[Codex MCP](https://developers.openai.com/codex/mcp)、[Kiro MCP](https://kiro.dev/docs/mcp/configuration/)、[Claude Code MCP](https://code.claude.com/docs/en/mcp)。
