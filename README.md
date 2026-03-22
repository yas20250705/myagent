# MyAgent

ターミナル上で自然言語の指示だけで開発作業を完結できる CLI AI コーディングエージェントです。LangGraph による ReAct ループと OpenAI / Gemini のマルチ LLM サポートを特徴とします。

## 特徴

- **自律的な開発支援** — ファイル操作・コード検索・シェル実行・Web検索を LLM が自律的に組み合わせてタスクを遂行
- **マルチ LLM 対応** — OpenAI と Google Gemini を切り替え可能。障害時は自動フォールバック
- **マルチエージェント並列実行** — Planner がサブタスクの依存関係を分析し、独立したタスクを並列実行
- **MCP 対応** — Model Context Protocol で外部サービス（GitHub・DB・Slack 等）のツールを動的追加
- **スキル / カスタムコマンド / プラグイン** — TOML や Markdown でワークフローを定義・共有・拡張
- **ストリーミング出力** — 生成テキストをリアルタイム表示し、ツール実行状況も可視化
- **セキュリティ制限** — プロジェクトルート外へのアクセス禁止、危険コマンドのブロック
- **LangSmith モニタリング** — トレース・LLM コスト・ツール実行を可視化（オプション）
- **REPL / ワンショット** — 対話型 REPL とワンショット実行の両モードに対応

## 必要環境

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) パッケージマネージャー
- OpenAI API キーまたは Google API キー

## インストール

```bash
git clone <repository-url>
cd MyCode
uv sync
```

> OneDrive など hardlink が使えない環境では `UV_LINK_MODE=copy uv sync` を使用してください。

### グローバルインストール（任意のディレクトリで `myagent` を実行）

```bash
uv tool install .
# OneDrive 環境の場合
uv tool install --link-mode=copy .
```

## 設定

### API キー

`.env.example` をコピーして `.env` を作成します。

```bash
cp .env.example .env
```

```env
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
EXA_API_KEY=your-exa-api-key...   # Web検索（オプション）

# LangSmith トレース（オプション）
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=ls__...
# LANGCHAIN_PROJECT=myagent
```

### 設定ファイル

設定は `~/.myagent/config.toml`（グローバル）または `.myagent/config.toml`（プロジェクトローカル）に保存されます。

```bash
# 現在の設定を確認
uv run myagent config

# LLM プロバイダを変更
uv run myagent set-config --provider gemini --model gemini-2.5-pro

# フォールバック先を変更
uv run myagent set-config --fallback-provider openai --fallback-model gpt-5-nano

# 確認レベルを変更 (strict / normal / autonomous)
uv run myagent set-config --confirmation-level autonomous
```

## 使い方

### REPL モード（対話型）

```bash
uv run myagent
```

```
myagent> src/myagent/cli/app.py の run_repl 関数の動作を説明して
myagent> tests/ を実行して失敗しているテストを修正して
myagent> git status を確認してコミットメッセージを提案して
myagent> exit
```

### ワンショットモード

```bash
uv run myagent --run "README.md を読んで、プロジェクト概要を100字で要約して"
uv run myagent -r "src/ 以下の Python ファイルを一覧表示して"
```

### REPL 内管理コマンド

エージェントを介さず直接実行できるコマンドです。スラッシュは省略可能です。

```
myagent> /help                          # ヘルプ表示
myagent> /stats                         # セッションメトリクス
myagent> /clear                         # 会話履歴のクリア
myagent> /config                        # 現在の設定を表示
myagent> /set-config --model gpt-5-nano # モデルを変更
myagent> /plugin list                   # プラグイン一覧
myagent> /skill list                    # スキル一覧
myagent> /mcp list                      # MCP サーバー一覧
```

## 利用可能なツール

| ツール | 説明 |
|--------|------|
| `read_file` | ファイルを行番号付きで読み取る |
| `write_file` | ファイルを新規作成・上書き |
| `edit_file` | ファイル内の指定文字列を置換 |
| `list_directory` | ディレクトリの一覧を表示 |
| `glob_search` | glob パターンでファイルを検索 |
| `grep_search` | 正規表現でファイル内容を検索 |
| `run_command` | シェルコマンドを実行（危険コマンドはブロック） |
| `web_search` | Web 検索（Exa / DuckDuckGo） |
| `web_fetch` | URL のページ内容を取得 |
| MCP ツール | 設定したMCPサーバーが提供するツール（動的追加） |

## アーキテクチャ

```
src/myagent/
├── cli/          # Click コマンド、Rich 表示、REPL、管理コマンドルーター
├── agent/        # LangGraph ReAct グラフ、Planner、Orchestrator、Critic
├── llm/          # LLMRouter（OpenAI/Gemini 切り替え、リトライ、フォールバック）
├── tools/        # ファイル操作・シェル・Web・MCP ツール、ToolRegistry
├── commands/     # カスタムコマンド（TOML 定義）
├── skills/       # スキル拡張（SKILL.md 定義）
├── plugins/      # プラグイン管理
└── infra/        # 設定管理、コンテキスト圧縮、カスタム例外
```

LangGraph の `StateGraph` で ReAct ループを実装しています。`agent_node` が LLM を呼び出し、ツール呼び出しが必要な場合は `tools` ノードへ遷移し、完了したら END に抜けます。Planner がタスクを複数のサブタスクに分解すると、Orchestrator が依存関係を解析して並列実行します。

## 開発

```bash
# テスト実行
uv run pytest

# カバレッジ付きテスト
uv run pytest --cov=src --cov-report=term-missing

# Lint
uv run ruff check src/ tests/

# フォーマット
uv run ruff format src/ tests/

# 型チェック
uv run mypy src/
```

### Dev Container

Visual Studio Code で「Reopen in Container」を選択すると、Python 3.12 環境と依存関係が自動でセットアップされます（Docker が必要です）。

## ドキュメント

| ファイル | 内容 |
|---------|------|
| [`docs/MANUAL.md`](docs/MANUAL.md) | 詳細な使い方・設定リファレンス |
| [`docs/product-requirements.md`](docs/product-requirements.md) | プロダクト要求定義書 |
| [`docs/architecture.md`](docs/architecture.md) | アーキテクチャ設計書 |

## ライセンス

MIT
