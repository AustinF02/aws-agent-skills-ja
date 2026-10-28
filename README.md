# AWS Agent Skills 日本語版

**Codex・Kiro・Claude Codeで、AWSのログインとMCP接続を日本語で進めるスキル集です。**

「どの設定ファイルを直すのか分からない」「AWS MCPだけ接続できない」「ログインが切れるたびに困る」ときに、既存設定を確認しながら導入と切り分けを進めます。利用者自身のAWSアカウントを使い、作者の認証情報・端末の設定は含めません。

[検証ワークフロー](https://github.com/AustinF02/aws-agent-skills-ja/actions/workflows/validate.yml)

> このリポジトリはAgent Skills形式のスキル集です。マーケットプレイスのワンクリック導入プラグインではありません。Claudeは **Claude Code** を対象とし、Claude Desktopや通常のWebチャットへの対応は保証しません。公開前の非公開状態では、他の利用者はアクセスできません。

## できること

| スキル | 用途 | AWSログイン |
| --- | --- | --- |
| [aws-knowledge-mcp-setup](skills/aws-knowledge-mcp-setup/SKILL.md) | 公式ドキュメントを検索するKnowledge MCPの接続 | 不要 |
| [aws-login-helper](skills/aws-login-helper/SKILL.md) | セッション失効の確認、必要な場合だけ再認証、AWS MCP起動 | 必要 |
| [aws-mcp-setup](skills/aws-mcp-setup/SKILL.md) | AWSアカウントを使う公式MCPの接続と切り分け | 必要 |
| [aws-agent-toolkit-setup](skills/aws-agent-toolkit-setup/SKILL.md) | AWS公式手順に沿うToolkit導入、AWSスキルとMCPの確認 | 必要 |

Knowledge MCPの接続だけなら、AWSアカウントやAWS CLIの準備から始める必要はありません。AWSリソースの操作まで必要になったときに、AWS MCPとログインを設定します。

## 最初に使う

利用するエージェントへ、次のように依頼してください。

```text
https://github.com/AustinF02/aws-agent-skills-ja のREADMEと対象スキルを読んでください。
まず aws-knowledge-mcp-setup を私の環境へ導入し、日本語で接続を確認してください。
既存設定は保持し、変更前に対象と差分を説明してください。
```

AWSへ接続する場合:

```text
aws-agent-toolkit-setup を使い、AWS公式setup.mdに沿って設定してください。
プロファイル名とリージョンは私に確認してください。
既存の認証方式、MCP設定、スキル、開発ルールは保持してください。
必要な認証操作は説明してから進めてください。
```

ログインの自動化を追加する場合:

```text
aws-login-helper を使い、AWS MCPの起動時に認証を確認してください。
有効ならそのまま起動し、失効時だけ再ログインしてください。
最初にOSとプロファイルを確認し、この環境で自動化できる範囲を説明してください。
```

GitHubを読めない環境では、対象スキルのフォルダをダウンロードして導入します。URLを渡しただけでインストール済みになるとは限りません。

## スキルの導入先

各 `skills/<スキル名>/` を、フォルダごと次の場所へ追加します。同名フォルダがある場合は、上書きせず内容を比較してください。

| エージェント | 個人用の導入先 |
| --- | --- |
| Codex | `~/.agents/skills/<スキル名>/` |
| Kiro | `~/.kiro/skills/<スキル名>/` |
| Claude Code | `~/.claude/skills/<スキル名>/` |

Codexは標準のskill-installerが利用できる場合、リポジトリURLと対象パスを指定して導入を依頼できます。保存先は利用中のバージョンの仕様を確認してください。

Kiroは「Agent Steering & Skills」から「Import a skill」を選び、例えば次の **スキルフォルダのURL** を指定します。リポジトリルートのURLではありません。

https://github.com/AustinF02/aws-agent-skills-ja/tree/main/skills/aws-knowledge-mcp-setup

Claude Codeではスキルフォルダを上記へ配置し、新しいセッションで `/aws-knowledge-mcp-setup` などを使います。Codexでは `$aws-knowledge-mcp-setup`、Kiroではスキル選択か自然文で依頼できます。

スキルの導入とMCPサーバーの接続設定は別作業です。各スキルが対象環境を確認して設定を案内します。

## ログイン補助の動作

同梱スクリプトはPython標準ライブラリのみを使います。実際の認証にはAWS CLI、MCP起動にはuvxとAWS公式proxyを使います。AWS CLI v2.32以上、Python 3.11以上が必要です。

1. 指定プロファイルでSTSへの接続を確認します。アカウントIDやARNは出力しません。
2. 有効ならログイン画面を開かず、AWS MCP proxyを起動します。
3. セッション失効と判定できた場合だけ、ブラウザー認証へ進みます。
4. ネットワーク障害や分類できないエラーでは、ログインせず停止します。
5. 同じプロファイルの同時起動はロックで調整します。

| 起動環境 | 再認証の扱い |
| --- | --- |
| macOS・端末 | 端末内で `aws login` を実行 |
| macOS・GUIアプリ | Terminalを開き、ブラウザー認証を待機 |
| Windows/Linux・端末 | 端末内で `aws login` を実行 |
| Windows/Linux・GUIアプリ | 自動で端末を開かず、端末からの再認証を案内 |
| SSH・ヘッドレス | 自動化の対象外。利用中の公式認証手順を使う |

**ブラウザー操作やMFAを省略する仕組みではありません。** macOSではTerminal操作のOS許可が必要な場合があります。待機は原則3分です。長引いた場合やキャンセル後は、認証を完了してからMCPを再接続してください。アプリ側の初期化タイムアウトによっては途中で切断されるため、単なる「アプリを開いた時刻」ではなく「MCP起動時」に実行します。

IAM Identity CenterのSSO、静的アクセスキー、credential_process等を、このヘルパーへ自動移行しません。選択プロファイルと親プロセスの環境変数による認証が混在しないよう、子プロセスではキー型の認証環境変数を引き継ぎません。環境変数型の認証を必要とする構成には適用しないでください。

### 手動確認

導入した `aws-login-helper` フォルダで実行します。`example-dev` は説明用の非秘密のプロファイル名です。自身の既存プロファイルとリージョンに置き換えてください。

```sh
python3 scripts/aws_mcp_login.py --profile example-dev --region ap-northeast-1 --check
python3 scripts/aws_mcp_login.py --profile example-dev --region ap-northeast-1 --login-only
```

Windowsではインストール済みのPythonコマンドを使ってください。MCP登録時は、各自の環境でPythonとスクリプトの絶対パスを解決します。作者のパスをコピーする必要はありません。

## 既存設定と安全性

- 同じ名前のMCPがあれば、先に動作と差分を確認します。設定ファイル全体は上書きしません。
- ログイン情報はAWS CLI自身が利用者の端末で管理します。本スクリプトは認証キャッシュを読み出したり、GitHubへ送信したりしません。
- ローカルに作るのは同時ログインを調整するロックファイルです。
- AWS MCP接続はIAM権限を新しく与えません。許可されたAWS操作には、変更や課金を伴うものがあります。書き込みの自動承認は設定しません。
- このリポジトリ、AWS、各エージェントの配布元を確認してから実行してください。proxyの初回起動では外部パッケージを取得します。
- 例のリージョンとプロファイルは初期値として強制しません。MCP接続先のリージョンと、ワークロードのリージョンは別です。
- `Invalid request parameters` だけで認証失効と断定せず、原因を確認します。

## 検証の範囲

GitHub ActionsでmacOS・Windows・Linux上の単体テストを実行します。入力検証、認証の有効/失効判定、ネットワーク障害時の停止、ログイン後の再確認などを、AWS認証を行わずに確認します。

これは各エージェントでのE2E接続、実際のブラウザー/MFA、macOSのTerminal許可、AWS側のIAM権限やサービス提供状況の検証ではありません。**Codex・Kiro・Claude Codeの全バージョンで動作確認済みとはしていません。**

```sh
python -m unittest discover -s tests -v
```

実装前の失敗記録と実装後の成功記録は、コミット履歴とActionsで確認できます。

## 開発方針

本リポジトリの [AGENTS.md](AGENTS.md) を開発方針の原本とします。Claude Codeは [CLAUDE.md](CLAUDE.md)、Kiroは [.kiro/steering/development.md](.kiro/steering/development.md) から参照します。`inclusion: always` はKiro用ファイルに一度だけ指定しています。

別プロジェクトに適用する場合は、AGENTS.mdの方針を既存ファイルへ統合してから、参照用ファイルを追加してください。既存の指示を丸ごと置換しないでください。

### おすすめの外部スキル

以下はリンクだけを紹介します。スキル本文、インストーラー、フックは同梱・自動導入しません。

- [TDD](https://github.com/intent-driven-dev/tdd-skill-evaluation-harness/tree/main/.codex/skills/tdd) — 失敗するテストから最小実装へ進める。
- [ponytail](https://github.com/DietrichGebert/ponytail) — 必要な変更に絞る。
- [caveman](https://github.com/JuliusBrussee/caveman) — 必要な事実を残して作業報告を短くする。

開発に使う場合は各配布元の導入条件・対応エージェント・ライセンスを確認してください。TDDリンクはCodex向けの実験的ハーネス内のスキルです。これらを未導入でもAWSセットアップ用の4スキルは利用できます。

## 公式資料

- [AWS Agent Toolkit セットアップ手順](https://raw.githubusercontent.com/aws/agent-toolkit-for-aws/refs/heads/main/setup-instructions/setup.md)
- [AWS Knowledge MCP](https://awslabs.github.io/mcp/servers/aws-knowledge-mcp-server)
- [AWS MCP Proxy](https://github.com/aws/mcp-proxy-for-aws)
- [AWS CLI login](https://docs.aws.amazon.com/cli/latest/reference/login/)
- [Codex Skills](https://developers.openai.com/codex/skills)
- [Kiro Skills](https://kiro.dev/docs/skills/)
- [Claude Code Skills](https://code.claude.com/docs/en/skills)

このリポジトリは個人による非公式プロジェクトです。AWS、OpenAI、Anthropicの公式配布物ではありません。公式手順は更新されるため、導入時点の内容を優先します。

## ライセンスと共有

本リポジトリで作成したコードと文章は [MIT License](LICENSE) です。リンク先の外部スキル・公式資料には、それぞれの利用条件が適用されます。

役立った場合はStarで応援していただけると励みになります。不具合報告には、OS、エージェントとバージョン、実行手順、秘密情報を除いたエラーの要点を添えてください。認証情報、AWSアカウントID、ARN、メールアドレス、ブラウザーの認証URLは投稿しないでください。
