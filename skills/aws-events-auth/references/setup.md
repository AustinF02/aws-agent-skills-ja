# 導入と検証

## 認証方式を選ぶ

AWS EventsはAWSアカウントのプロファイルではなく、AWS Builder IDを使う。この認証にAWS CLI導入やIAM権限の変更は不要。イベントへの登録は別途確認する。

動作中の標準MCP接続を優先し、設定前に現行の[AWS公式MCP手順](https://docs.aws.amazon.com/events/latest/devguide/mcp-server.html)を読む。

- **Kiro:** 公式のawsevents HTTP設定、公開client ID、scope、ポート8976で終わるredirectUriを使う。コールバックのパスはKiroが追加するため、重ねて指定しない。
- **Claude Code:** 公式コマンドはコールバックポート8484と共通の公開client IDを使う。承認範囲で既存設定へ追加する。
- **Codex:** 利用バージョンのOAuth・ヘッダーヘルパー対応と、生成されるコールバック全体を確認する。AWSはホスト・ポート・パスを完全一致で照合する。redirect mismatchを繰り返したり、動作中の接続を無断で置換しない。

接続先は https://api.awsevents.com/mcp 。公開client IDは7vmom55m1qstvq8i71ph127bfq、scopeはopenid、email、events/access。これらは公開のプロトコル設定で、認証情報ではない。access tokenの代わりにIAMキーやID tokenを使わない。

## 同梱するmacOS用の代替ヘルパー

macOS、Python 3.11以上、バージョン固定の [requirements-macos.txt](../requirements-macos.txt) が必要。Windows/Linuxでは対応するクライアントのOAuthを使う。同梱スクリプトはKeychainへのアクセスやブラウザー起動の前に停止する。

導入したスキルのディレクトリで実行する。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-macos.txt
.venv/bin/python scripts/events_auth.py login
```

loginは承認後に実行する。Builder ID・MFAはブラウザー内で完了し、URL・コード・トークンをチャットへ転記しない。スクリプトはloopbackのみを待ち受け、毎回新しいPKCE・stateと、公式のコールバックポート8484–8489を使う。

トークンは利用者自身のmacOS Keychainに、汎用のサービス名aws-agent-skills.aws-events-authで保持する。作者のトークン、Keychain書き出し、キャッシュ、プロファイル、アカウント識別子は同梱しない。既存のKeychain項目を削除せず更新し、保存失敗時は停止する。ネイティブ保存処理は固定したkeyringバージョンを使うため、更新前に互換性を確認する。ローカルのrefresh.lockで同時更新を調整する。

```sh
.venv/bin/python scripts/events_auth.py status
.venv/bin/python scripts/events_auth.py get "/v1/events/example-event/schedule"
```

example-eventは利用者が選んだイベントIDへ置き換える。statusは状態だけを表示する。getのJSONには個人の予定が含まれるため、公開ログへ残さない。getはトークンを引数や環境変数へコピーせず、内部でBearerヘッダーを付ける。refreshはブラウザーを開かず既存セッションを更新する。標準クライアントと本ヘルパーのトークン保存先は別。

### Codexのヘッダー連携

利用バージョンが対応する場合だけ、venvのPythonとスクリプトの絶対パスを解決し、必要な引用符を付けてawseventsの項目へ追加する。

```toml
[mcp_servers.awsevents]
url = "https://api.awsevents.com/mcp"
http_headers_helper = "<ABSOLUTE_PYTHON_PATH> <ABSOLUTE_SCRIPT_PATH> headers"
```

仮のパスをそのまま実行したり、headersの出力を表示しない。RESTラッパーの再試行はgetに適用される。MCP側の再試行・ヘッダー優先順位はクライアントが制御する。任意のcurl・MCP呼び出しを自動的に横取りすると説明しない。明示的な承認なしに既存のOAuthを置換しない。

## 復旧と確認

- 401は一度だけ更新・再試行。再度401になる、または更新が拒否される場合は、承認済みの対話ログインへ進む。
- 403はイベント登録・認可を確認する。再ログインで登録権限は増えない。
- 通信障害では停止して調査し、ログインを開かない。
- Keychain障害ではOSのアクセス許可を確認する。トークンの書き出し、既存項目の削除、平文保存へ逃げない。
- 設定保存やトークン更新だけでMCP接続済みとしない。ツール一覧と依頼された読み取りを確認する。公開カタログの成功だけでは個人予定を確認できない。
- セッションのページングはnextTokenがなくなるまで。読み取り件数・時間を制限する。
- 配布ヘルパーのテストはOAuth・Keychainをモック化する。元のローカル手順はmacOSで実施したが、全エージェント・全バージョンのE2E検証済みとはしない。

参照: [開始手順](https://docs.aws.amazon.com/events/latest/devguide/getting-started.html)、[PKCE認証](https://docs.aws.amazon.com/events/latest/devguide/auth-signing-in.html)、[更新](https://docs.aws.amazon.com/events/latest/devguide/auth-refreshing.html)、[公開エンドポイントとclient ID](https://docs.aws.amazon.com/events/latest/devguide/auth-endpoints.html)、[Codex MCP](https://learn.chatgpt.com/docs/extend/mcp)。
