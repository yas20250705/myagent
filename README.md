# MyAgent

ターミナル上で自然言語の指示だけで開発作業を完結できる CLI AI コーディングエージェントです。LangGraph による ReAct ループと OpenAI / Gemini のマルチ LLM サポートを特徴とします。

## 特徴

- **自律的な開発支援** — ファイル操作・コード検索・シェル実行を LLM が自律的に組み合わせてタスクを遂行
- **マルチ LLM 対応** — OpenAI (gpt-4o-mini) と Google Gemini (gemini-2.0-flash) を切り替え可能。障害時は自動フォールバック
- **ストリーミング出力** — 生成テキストをリアルタイム表示し、ツール実行状況も可視化
- **セキュリティ制限** — プロジェクトルート外へのアクセス禁止、危険コマンドのブロック
- **REPL / ワンショット** — 対話型 REPL とワンショット実行の両モードに対応

## 必要環境

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) パッケージマネージャー
- OpenAI API キーまたは Google API キー

## インストール

```bash
git clone <repository-url>
cd myagent
uv sync
```

> OneDrive など hardlink が使えない環境では `UV_LINK_MODE=copy uv sync` を使用してください。

## 設定

### API キー

環境変数で設定します。

```bash
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="AIza..."
```

### 設定ファイル

設定は `~/.myagent/config.toml` に保存されます。CLI コマンドで変更できます。

```bash
# 現在の設定を確認
uv run myagent config

# LLM プロバイダを変更 (openai / gemini)
uv run myagent set-config --provider gemini

# モデルを変更
uv run myagent set-config --model gemini-2.0-flash
```

## 使い方

### REPL モード（対話型）

```bash
uv run myagent
```

プロンプトが表示されたら自然言語で指示を入力します。`exit` または `quit` で終了します。

```
指示 > src/myagent/cli/app.py の run_repl 関数の動作を説明して
指示 > tests/ 内のテストを全部確認して失敗しそうな箇所を教えて
指示 > exit
```

### ワンショットモード

```bash
uv run myagent "README.md を読んで、プロジェクト概要を100字で要約して"
```

## 利用可能なツール

エージェントは以下のツールを使ってタスクを遂行します。

| ツール | 説明 |
|--------|------|
| `read_file` | ファイルを行番号付きで読み取る |
| `write_file` | ファイルを新規作成・上書き |
| `edit_file` | ファイル内の指定文字列を置換 |
| `list_directory` | ディレクトリの一覧を表示 |
| `glob_search` | glob パターンでファイルを検索 |
| `grep_search` | 正規表現でファイル内容を検索 |
| `run_command` | シェルコマンドを実行（危険コマンドはブロック） |

すべてのファイルアクセスはプロジェクトルートに制限されます。

## アーキテクチャ

```
src/myagent/
├── cli/          # click コマンド、Rich 表示、prompt_toolkit REPL
├── agent/        # LangGraph ReAct グラフ、AgentRunner、AgentEvent
├── llm/          # LLMRouter（OpenAI/Gemini 切り替え、リトライ、フォールバック）
├── tools/        # ファイル操作・シェル実行ツール群、ToolRegistry
└── infra/        # 設定管理、カスタム例外
```

LangGraph の `StateGraph` で ReAct ループを実装しています。`agent_node` が LLM を呼び出し、ツール呼び出しが必要な場合は `tools` ノードへ遷移し、完了したら END に抜けます。

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
uv run mypy
```

テストは `tests/unit/` 以下に配置されており、118 テスト・カバレッジ 70% 以上を維持しています。

### Dev Container

Visual Studio Code で「Reopen in Container」を選択すると、Python 3.12 環境と依存関係が自動でセットアップされます（Docker が必要です）。

## ライセンス

MIT
