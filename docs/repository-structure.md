# リポジトリ構造定義書 (Repository Structure Document)

## プロジェクト構造

```
myagent/
├── src/
│   └── myagent/               # メインパッケージ
│       ├── __init__.py
│       ├── main.py            # エントリーポイント
│       ├── cli/               # CLIレイヤー
│       │   ├── __init__.py
│       │   ├── app.py         # REPL・対話制御
│       │   ├── commands.py    # clickコマンド定義
│       │   └── display.py     # Rich表示・レンダリング
│       ├── agent/             # エージェントレイヤー
│       │   ├── __init__.py
│       │   ├── graph.py       # LangGraphステートマシン定義
│       │   ├── planner.py     # タスク分解・計画
│       │   ├── executor.py    # ツール実行制御
│       │   ├── critic.py      # 結果評価・再試行判断
│       │   ├── state.py       # AgentState定義
│       │   └── events.py      # AgentEvent定義
│       ├── llm/               # LLMレイヤー
│       │   ├── __init__.py
│       │   ├── router.py      # プロバイダ切替・フォールバック
│       │   ├── openai.py      # OpenAIプロバイダ
│       │   └── gemini.py      # Geminiプロバイダ
│       ├── tools/             # ツールレイヤー
│       │   ├── __init__.py
│       │   ├── registry.py    # ツール登録・管理
│       │   ├── file_tools.py  # ファイル操作ツール
│       │   ├── shell_tools.py # シェル実行ツール
│       │   ├── git_tools.py   # Git操作ツール
│       │   ├── search_tools.py # コード検索ツール
│       │   └── test_tools.py  # テスト実行ツール
│       └── infra/             # インフラレイヤー
│           ├── __init__.py
│           ├── config.py      # 設定管理
│           ├── logger.py      # ログ出力
│           └── context.py     # コンテキスト管理・圧縮
├── tests/                     # テストコード
│   ├── __init__.py
│   ├── conftest.py            # 共通フィクスチャ
│   ├── unit/                  # ユニットテスト
│   │   ├── __init__.py
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   ├── test_planner.py
│   │   │   ├── test_executor.py
│   │   │   ├── test_critic.py
│   │   │   └── test_state.py
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   └── test_router.py
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── test_file_tools.py
│   │   │   ├── test_shell_tools.py
│   │   │   ├── test_git_tools.py
│   │   │   ├── test_search_tools.py
│   │   │   └── test_test_tools.py
│   │   └── infra/
│   │       ├── __init__.py
│   │       ├── test_config.py
│   │       └── test_context.py
│   ├── integration/           # 統合テスト
│   │   ├── __init__.py
│   │   ├── test_agent_loop.py
│   │   ├── test_tool_execution.py
│   │   └── test_llm_fallback.py
│   └── e2e/                   # E2Eテスト
│       ├── __init__.py
│       ├── test_interactive_mode.py
│       └── test_oneshot_mode.py
├── docs/                      # プロジェクトドキュメント
│   ├── ideas/                 # アイデア・壁打ちメモ
│   │   └── idea2.md
│   ├── product-requirements.md
│   ├── functional-design.md
│   ├── architecture.md
│   ├── repository-structure.md
│   ├── development-guidelines.md
│   └── glossary.md
├── .steering/                 # 作業単位のドキュメント
├── .claude/                   # Claude Code設定
├── .devcontainer/             # devcontainer設定
├── pyproject.toml             # プロジェクト設定・依存関係
├── README.md                  # プロジェクト概要
├── LICENSE                    # ライセンス
└── .gitignore                 # Git除外設定
```

---

## ディレクトリ詳細

### src/myagent/ (ソースコードディレクトリ)

#### cli/

**役割**: ユーザー入力の受付、ストリーミング表示、確認プロンプト、Markdownレンダリング

**配置ファイル**:
- `app.py`: REPL（対話モード）の起動・制御、prompt_toolkitによる入力処理
- `commands.py`: clickによるCLIコマンド定義（`myagent`, `myagent config`等）
- `display.py`: Richによる表示制御（ストリーミング出力、スピナー、テーブル、差分表示）

**命名規則**:
- モジュールファイル: snake_case
- CLIコマンド関連の関数: `cmd_` プレフィックス不要、clickデコレータで定義

**依存関係**:
- 依存可能: `agent/`（AgentCore呼び出し）、`infra/`（Config, Logger）
- 依存禁止: `llm/`, `tools/`（エージェントレイヤーを経由する）

---

#### agent/

**役割**: LangGraphステートマシンによるPlan-Execute-Criticループの制御

**配置ファイル**:
- `graph.py`: LangGraphのStateGraph定義、ノード・エッジの接続
- `planner.py`: Plannerノード実装（タスク分解・計画立案）
- `executor.py`: Executorノード実装（ツール呼び出し・確認フロー制御）
- `critic.py`: Criticノード実装（結果評価・無限ループ検知）
- `state.py`: AgentState, SubTask, ToolCall等のデータクラス定義
- `events.py`: AgentEvent, EventType等のイベント定義

**命名規則**:
- 各ノードは独立したモジュールファイルに配置
- データクラスは `state.py` に集約

**依存関係**:
- 依存可能: `llm/`（LLM呼び出し）、`tools/`（ツール実行）、`infra/`（Config, Logger, Context）
- 依存禁止: `cli/`（AgentEventを通じて間接通知）

---

#### llm/

**役割**: LLMプロバイダの抽象化、フォールバック制御、リトライ、トークン追跡

**配置ファイル**:
- `router.py`: LLMRouterクラス（プロバイダ選択・フォールバック・リトライロジック）
- `openai.py`: OpenAIプロバイダのラッパー（ChatOpenAI設定・初期化）
- `gemini.py`: Geminiプロバイダのラッパー（ChatGoogleGenerativeAI設定・初期化）

**命名規則**:
- プロバイダファイル: プロバイダ名をそのまま使用（`openai.py`, `gemini.py`）
- 新規プロバイダ追加時: `{provider_name}.py` として追加

**依存関係**:
- 依存可能: `infra/`（Config, Logger）
- 依存禁止: `agent/`, `tools/`, `cli/`

---

#### tools/

**役割**: ファイル操作、シェル実行、Git操作等の外部システムとのインタラクション

**配置ファイル**:
- `registry.py`: ToolRegistryクラス（ツール登録・一覧・ディスパッチ）
- `file_tools.py`: read_file, write_file, edit_file, list_directory, glob_search, grep_search
- `shell_tools.py`: run_command（危険コマンド検知含む）
- `git_tools.py`: git_status, git_diff, git_log, git_commit, git_branch, git_checkout
- `search_tools.py`: コード検索特化ツール（grep_search, glob_search の拡張）
- `test_tools.py`: run_tests（pytest実行・結果解析）

**命名規則**:
- ファイル名: `{カテゴリ}_tools.py`
- 各ファイル内のツールクラス: LangChain `BaseTool` を継承、`{ToolName}Tool` 形式

**依存関係**:
- 依存可能: `infra/`（Config, Logger）
- 依存禁止: `agent/`, `llm/`, `cli/`

---

#### infra/

**役割**: 設定管理、ログ出力、コンテキスト管理（横断的関心事）

**配置ファイル**:
- `config.py`: AppConfig, LLMConfig等のpydanticモデル、config.tomlの読み書き
- `logger.py`: JSON形式ログ出力、トークン使用量追跡、ログローテーション
- `context.py`: ContextManagerクラス（会話履歴管理、トークン計算、圧縮、プロジェクトインデックス）

**命名規則**:
- モジュールファイル: 横断的関心事の名前をそのまま使用

**依存関係**:
- 依存可能: なし（他レイヤーから依存される側）
- 依存禁止: `cli/`, `agent/`, `llm/`, `tools/`

---

### tests/ (テストディレクトリ)

#### unit/

**役割**: 各コンポーネントの個別ロジックのテスト

**構造**: `src/myagent/` のディレクトリ構造をミラーリング
```
tests/unit/
├── agent/
│   └── test_planner.py      # src/myagent/agent/planner.py のテスト
├── llm/
│   └── test_router.py       # src/myagent/llm/router.py のテスト
├── tools/
│   └── test_file_tools.py   # src/myagent/tools/file_tools.py のテスト
└── infra/
    └── test_config.py       # src/myagent/infra/config.py のテスト
```

**命名規則**:
- パターン: `test_{テスト対象ファイル名}.py`
- テスト関数: `test_{テスト対象メソッド}_{シナリオ}`
- 例: `test_planner_generates_subtasks_for_simple_instruction`

#### integration/

**役割**: 複数コンポーネントの結合動作テスト

**構造**: 機能・フロー単位でファイルを配置
```
tests/integration/
├── test_agent_loop.py        # Agent Core → Tools の一連のフロー
├── test_tool_execution.py    # ToolRegistry → 各Tool の結合
└── test_llm_fallback.py      # LLMRouter フォールバックフロー
```

**命名規則**:
- パターン: `test_{テスト対象フロー}.py`

#### e2e/

**役割**: CLIからのエンドツーエンドテスト

**構造**: ユーザーシナリオ単位でファイルを配置
```
tests/e2e/
├── test_interactive_mode.py  # 対話モードのシナリオ
└── test_oneshot_mode.py      # ワンショット実行のシナリオ
```

**命名規則**:
- パターン: `test_{ユーザーシナリオ}.py`
- `@pytest.mark.e2e` マーカーを付与（CI環境でスキップ可能にする）

---

### docs/ (ドキュメントディレクトリ)

**配置ドキュメント**:
- `product-requirements.md`: プロダクト要求定義書
- `functional-design.md`: 機能設計書
- `architecture.md`: アーキテクチャ設計書
- `repository-structure.md`: リポジトリ構造定義書（本ドキュメント）
- `development-guidelines.md`: 開発ガイドライン
- `glossary.md`: 用語集
- `ideas/`: アイデア・壁打ちメモ

---

## ファイル配置規則

### ソースファイル

| ファイル種別 | 配置先 | 命名規則 | 例 |
|------------|--------|---------|-----|
| CLIコマンド | `src/myagent/cli/` | `{機能}.py` | `commands.py`, `display.py` |
| エージェントノード | `src/myagent/agent/` | `{ノード名}.py` | `planner.py`, `critic.py` |
| LLMプロバイダ | `src/myagent/llm/` | `{プロバイダ名}.py` | `openai.py`, `gemini.py` |
| ツール | `src/myagent/tools/` | `{カテゴリ}_tools.py` | `file_tools.py`, `git_tools.py` |
| インフラ | `src/myagent/infra/` | `{関心事}.py` | `config.py`, `logger.py` |
| データクラス | `src/myagent/agent/state.py` | クラス名: PascalCase | `AgentState`, `SubTask` |
| イベント | `src/myagent/agent/events.py` | クラス名: PascalCase | `AgentEvent` |

### テストファイル

| テスト種別 | 配置先 | 命名規則 | 例 |
|-----------|--------|---------|-----|
| ユニットテスト | `tests/unit/{レイヤー}/` | `test_{対象}.py` | `test_planner.py` |
| 統合テスト | `tests/integration/` | `test_{フロー}.py` | `test_agent_loop.py` |
| E2Eテスト | `tests/e2e/` | `test_{シナリオ}.py` | `test_interactive_mode.py` |

### 設定ファイル

| ファイル種別 | 配置先 | 説明 |
|------------|--------|------|
| プロジェクト設定 | `pyproject.toml` | 依存関係、ruff/mypy設定、pytest設定 |
| Git除外 | `.gitignore` | バージョン管理から除外するファイル |
| devcontainer | `.devcontainer/` | 開発コンテナ設定 |

---

## 命名規則

### ディレクトリ名

- **レイヤーディレクトリ**: snake_case（Pythonパッケージとして機能するため）
  - 例: `cli/`, `agent/`, `llm/`, `tools/`, `infra/`
- **テストディレクトリ**: snake_case
  - 例: `unit/`, `integration/`, `e2e/`

### ファイル名

- **モジュールファイル**: snake_case
  - 例: `planner.py`, `file_tools.py`, `context.py`
- **テストファイル**: `test_` プレフィックス + snake_case
  - 例: `test_planner.py`, `test_file_tools.py`

### クラス名・関数名

- **クラス名**: PascalCase
  - 例: `AgentCore`, `LLMRouter`, `ToolRegistry`
- **関数名**: snake_case
  - 例: `run_command`, `read_file`, `build_graph`
- **定数**: UPPER_SNAKE_CASE
  - 例: `MAX_ITERATIONS`, `BLOCKED_PATTERNS`

---

## 依存関係のルール

### レイヤー間の依存

```
CLI レイヤー (cli/)
    ↓ (OK)
エージェントレイヤー (agent/)
    ↓ (OK)            ↓ (OK)
LLM レイヤー (llm/)   ツールレイヤー (tools/)

インフラレイヤー (infra/) ← 全レイヤーから依存可能
```

**禁止される依存**:
- `llm/` → `agent/` (逆方向依存)
- `tools/` → `agent/` (逆方向依存)
- `tools/` → `llm/` (レイヤー横断)
- `llm/` → `tools/` (レイヤー横断)
- 全レイヤー → `cli/` (CLIへの逆方向依存)
- `infra/` → 他の全レイヤー (インフラは依存される側)

### 循環依存の回避

エージェントレイヤーからCLIレイヤーへの通知が必要な場合、`AgentEvent` を介して間接的に行う:

```python
# agent/events.py（エージェントレイヤー）
@dataclass
class AgentEvent:
    type: EventType
    data: dict[str, Any]

# cli/app.py（CLIレイヤー）
async for event in agent.run(instruction):
    # イベントを受け取って表示
    match event.type:
        case "stream_token":
            display.stream(event.data["token"])
        case "confirm_request":
            approved = display.ask_confirmation(event.data["message"])
```

---

## スケーリング戦略

### ツールの追加

新しいツールカテゴリを追加する場合:

1. `src/myagent/tools/{category}_tools.py` を作成
2. LangChain `BaseTool` を継承したツールクラスを実装
3. `registry.py` で自動登録（または明示的に登録）

```python
# 例: docker_tools.py を追加
src/myagent/tools/
├── registry.py
├── file_tools.py
├── shell_tools.py
├── git_tools.py
├── search_tools.py
├── test_tools.py
└── docker_tools.py    # 新規追加
```

### LLMプロバイダの追加

新しいLLMプロバイダを追加する場合:

1. `src/myagent/llm/{provider}.py` を作成
2. LangChainのChatModel準拠のラッパーを実装
3. `router.py` にプロバイダを登録

### ファイルサイズの管理

- 1ファイル: 300行以下を推奨
- 300-500行: リファクタリングを検討
- 500行以上: 分割を強く推奨

分割例: `file_tools.py` が肥大化した場合
```
tools/
├── file_tools/
│   ├── __init__.py          # 公開インターフェース
│   ├── read_tools.py        # read_file
│   ├── write_tools.py       # write_file, edit_file
│   └── search_tools.py      # glob_search, grep_search
```

---

## 特殊ディレクトリ

### .steering/ (ステアリングファイル)

**役割**: 特定の開発作業における「今回何をするか」を定義

**構造**:
```
.steering/
└── 20260320-implement-cli/
    ├── requirements.md
    ├── design.md
    └── tasklist.md
```

**命名規則**: `YYYYMMDD-{task-name}` 形式

### .claude/ (Claude Code設定)

**役割**: Claude Code設定とカスタマイズ

**構造**:
```
.claude/
├── commands/
├── skills/
└── agents/
```

---

## 除外設定

### .gitignore

```
# Python
__pycache__/
*.pyc
*.pyo
.venv/
*.egg-info/
dist/
build/

# 環境設定
.env
.env.*

# ツールキャッシュ
.mypy_cache/
.pytest_cache/
.ruff_cache/
htmlcov/

# OS
.DS_Store
Thumbs.db

# ログ
*.log

# ステアリング（作業用一時ファイル）
.steering/

# IDE
.idea/
.vscode/
```

### pyproject.toml 除外設定

```toml
[tool.ruff]
exclude = [".venv", ".steering", "htmlcov"]

[tool.mypy]
exclude = [".venv", ".steering", "htmlcov"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["e2e: end-to-end tests (deselect with '-m \"not e2e\"')"]
```
