# MyAgent 取り扱い手順書

**MyAgent** は LangGraph ベースの CLI AI コーディングエージェントです。
自然言語の指示でファイル操作・コード検索・Git 操作・テスト実行などをエージェントが自律的に実行します。

---

## 目次

1. [前提条件・セットアップ](#1-前提条件セットアップ)
2. [APIキーの設定](#2-apiキーの設定)
3. [起動方法](#3-起動方法)
4. [基本的な使い方](#4-基本的な使い方)
5. [REPL内コマンド一覧](#5-repl内コマンド一覧)
6. [設定管理](#6-設定管理)
7. [カスタムコマンド（F16）](#7-カスタムコマンドf16)
8. [スキル拡張（F14）](#8-スキル拡張f14)
9. [プラグイン管理（F15）](#9-プラグイン管理f15)
10. [MCP サーバー連携](#10-mcpサーバー連携)
11. [LangSmith モニタリング](#11-langsmithモニタリング)
12. [開発者向け手順](#12-開発者向け手順)
13. [トラブルシューティング](#13-トラブルシューティング)
14. [ディレクトリ構造](#14-ディレクトリ構造)

---

## 1. 前提条件・セットアップ

### 必要環境

| 項目 | 要件 |
|------|------|
| OS | Windows（WSL推奨）/ macOS / Linux |
| Python | 3.12 以上 |
| パッケージマネージャー | [uv](https://docs.astral.sh/uv/) |

### インストール手順

#### 開発版（リポジトリから実行）

```bash
# 1. リポジトリのクローン
git clone <repository-url>
cd MyCode

# 2. 依存関係のインストール
uv sync

# 3. 動作確認
uv run myagent --help
```

#### グローバルインストール（任意のディレクトリで利用）

グローバルインストールすると、任意のディレクトリで `myagent` コマンドを直接実行できます。

```bash
# 方法1: uv tool install（推奨）
uv tool install .          # リポジトリルートで実行

# 方法2: pip install
pip install .              # リポジトリルートで実行
```

インストール後の確認:

```bash
# バージョン確認
myagent --version

# 任意のプロジェクトディレクトリで起動
cd ~/my-project
myagent                    # REPL が起動し、カレントディレクトリが作業ディレクトリになる
```

#### アンインストール

```bash
# uv tool install でインストールした場合
uv tool uninstall myagent

# pip install でインストールした場合
pip uninstall myagent
```

---

## 2. APIキーの設定

`.env.example` をコピーして `.env` を作成し、APIキーを設定します。

```bash
cp .env.example .env
```

`.env` を編集:

```env
# OpenAI API Key（メインLLM）
OPENAI_API_KEY=sk-...

# Google API Key（Gemini / フォールバックLLM）
GOOGLE_API_KEY=AIza...

# Exa AI API Key（Web検索ツール・オプション）
EXA_API_KEY=your-exa-api-key...

# LangSmith（トレース・モニタリング・オプション）
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=ls__...
# LANGCHAIN_PROJECT=myagent
```

### APIキーの優先順位

1. プロジェクトの `.env`（起動ディレクトリ）
2. `~/.myagent/.env`（グローバル設定）
3. システム環境変数

> **注意**: `.env` ファイルは `.gitignore` に含まれており、リポジトリにはコミットされません。

---

## 3. 起動方法

### 対話モード（REPL）

ターミナルで以下を実行するとプロンプトが表示されます。

```bash
uv run myagent
```

```
# myagent
AIコーディングアシスタント

`exit` で終了、`/help` でヘルプを表示

作業ディレクトリ: /your/project/path
myagent>
```

### ワンショット実行

単発の指示を引数として渡します。

```bash
uv run myagent --run "src/ 以下の Python ファイルを一覧表示して"
# または短縮形
uv run myagent -r "README.md を読んで内容を要約して"
```

### カスタムコマンドをワンショット実行

```bash
uv run myagent --command test-fix --command-args '--test_command "pytest -x"'
# または短縮形
uv run myagent -c test-fix --command-args '--test_command "pytest -x"'
```

### 設定ファイルを指定して起動

```bash
uv run myagent --config /path/to/config.toml
```

### 作業ディレクトリを明示指定して起動

```bash
uv run myagent --working-dir /path/to/project
```

---

## 4. 基本的な使い方

REPL モードで自然言語の指示を入力するだけで動作します。

```
myagent> このディレクトリの Python ファイルを一覧表示して
myagent> src/myagent/cli/app.py を読んで処理の流れを説明して
myagent> tests/ を実行して失敗しているテストを修正して
myagent> git status を確認してコミットメッセージを提案して
```

### エージェントの思考ループ

入力を受け取ると、エージェントは以下のサイクルを繰り返します:

```
Planning（タスク分解）
  ↓
Executing（ツール実行）
  ↓
Evaluating（結果評価・エラー繰り返し検知）
  ↓
完了 または 次のステップへ
```

### ユーザー確認フロー

ファイル編集・シェルコマンド実行など**副作用のある操作**では確認プロンプトが表示されます。

```
⚠ ファイルを編集します: src/module.py

  --- 変更前
  +++ 変更後
  @@ -10,3 +10,5 @@
   def calculate():
  -    return x + y
  +    if x is None:
  +        raise ValueError("x must not be None")
  +    return x + y

適用しますか？ [y]es / [n]o:
```

`n` を選択するとそのツール実行をキャンセルし、エージェントを停止します。

---

## 5. REPL内コマンド一覧

### 組み込みコマンド

| コマンド | 動作 |
|---------|------|
| `exit` / `quit` / `q` | エージェントを終了する |
| `/help` / `help` | ヘルプとカスタムコマンド一覧を表示する |
| `/stats` / `stats` | セッションメトリクス（ツール呼び出し回数・成功率）を表示する |
| `/status` / `status` | 現在のセッション状態（ステップ数・トークン使用量）を表示する |
| `/clear` / `clear` | 会話履歴をクリアする |

> スラッシュは省略可能です（`stats`、`clear` 等でも動作します）。

### 管理コマンド（スラッシュ形式）

REPL 内からエージェントを経由せず直接実行できる管理コマンドです。

#### プラグイン管理

| コマンド | 動作 |
|---------|------|
| `/plugin list` | インストール済みプラグインの一覧を表示する |
| `/plugin install <git-url-or-path>` | プラグインをインストールする |
| `/plugin uninstall <name>` | プラグインをアンインストールする |
| `/plugin enable <name>` | プラグインを有効化する |
| `/plugin disable <name>` | プラグインを無効化する |
| `/plugin validate [path]` | マニフェストを検証する |

#### スキル管理

| コマンド | 動作 |
|---------|------|
| `/skill list` | スキル一覧を表示する |
| `/skill info <skill-name>` | スキルの詳細情報を表示する |
| `/skill validate <path>` | SKILL.md を検証する |
| `/skill install <git-url-or-path>` | スキルをグローバル（`~/.myagent/skills`）にインストールする |
| `/skill install <git-url-or-path> --local` | スキルをプロジェクトローカルにインストールする |
| `/skill uninstall <skill-name>` | スキルを削除する |

#### カスタムコマンド管理

| コマンド | 動作 |
|---------|------|
| `/command list` | 登録済みカスタムコマンドの一覧を表示する |
| `/command init <name>` | プロジェクトローカルのコマンド雛形を生成する |
| `/command init <name> --global` | グローバルコマンド雛形を生成する |

#### 設定管理

| コマンド | 動作 |
|---------|------|
| `/config` | 現在の設定内容を表示する |
| `/set-config --provider <name>` | LLMプロバイダを変更する |
| `/set-config --model <name>` | プライマリモデルを変更する |
| `/set-config --fallback-provider <name>` | フォールバックプロバイダを変更する |
| `/set-config --fallback-model <name>` | フォールバックモデルを変更する |
| `/set-config --confirmation-level <level>` | 確認レベルを変更する |

> `setconfig`（ハイフンなし）もエイリアスとして使用可能です。

#### MCP管理

| コマンド | 動作 |
|---------|------|
| `/mcp list` | MCPサーバー一覧と接続状態を表示する |
| `/mcp test <name>` | 指定サーバーへの接続テストを実行する |

### カスタムコマンド呼び出し

登録済みのカスタムコマンドはスラッシュ形式で呼び出せます。

```
myagent> /test-fix --test_command "pytest tests/unit/"
myagent> /doc-gen --target src/myagent/cli/
```

---

## 6. 設定管理

### 設定ファイルの場所と優先順位

| パス | 用途 | 優先度 |
|------|------|--------|
| `--config <path>` 指定 | 任意のパスの設定ファイル | 最高 |
| `.myagent/config.toml`（起動ディレクトリ） | プロジェクトローカル設定 | 高 |
| `~/.myagent/config.toml` | グローバル設定 | 基底 |

プロジェクトローカル設定はグローバル設定にマージされ、同一キーはプロジェクト設定が優先されます。

### 設定内容の確認

```bash
# CLIサブコマンド
uv run myagent config

# REPL内でも確認可能
myagent> /config
```

### 設定の変更

```bash
# LLMプロバイダをGeminiに変更
uv run myagent set-config --provider gemini

# プライマリモデルを指定
uv run myagent set-config --model gemini-2.5-pro

# フォールバックモデルを指定
uv run myagent set-config --fallback-provider openai --fallback-model gpt-5-nano

# 確認レベルの変更
uv run myagent set-config --confirmation-level autonomous
```

### 確認レベル（`confirmation_level`）

| レベル | 動作 |
|--------|------|
| `strict` | ファイル読み込みも含め全操作で確認を求める |
| `normal` | ファイル編集・シェル実行などで確認を求める（デフォルト） |
| `autonomous` | 全操作を自動実行する（危険な操作は除く） |

### config.toml の全設定項目

```toml
[llm]
provider = "openai"                # メインプロバイダ: "openai" or "gemini"
model = "gpt-5-nano"               # モデル名
fallback_provider = "gemini"       # フォールバックプロバイダ
fallback_model = "gemini-3.1-flash-lite-preview"
max_retries = 3                    # APIエラー時の最大リトライ回数
temperature = 0.0                  # 生成温度 (0.0 〜 2.0)

[tool]
confirmation_level = "normal"      # 確認レベル: "strict" / "normal" / "autonomous"
max_output_lines = 200             # ツール出力の最大行数
allowed_directories = []           # ファイルアクセスを許可する追加ディレクトリ

[agent]
max_loops = 20                     # 最大ループ回数
context_window_tokens = 128000     # コンテキストウィンドウサイズ
max_parallel_workers = 3           # マルチエージェント並列実行の最大ワーカー数 (1〜10)

[command]
project_commands_dir = ".myagent/commands"   # プロジェクトコマンドディレクトリ
global_commands_dir = ""                     # グローバルコマンドディレクトリ（空 = ~/.myagent/commands）

[skill]
project_skills_dir = ".myagent/skills"       # プロジェクトスキルディレクトリ
global_skills_dir = ""                       # グローバルスキルディレクトリ（空 = ~/.myagent/skills）

[plugin]
enabled_plugins = []               # 有効化するプラグイン名のリスト
plugin_dirs = []                   # 開発用追加プラグインディレクトリ

[web_search]
timeout = 25
default_num_results = 5
fallback_enabled = true
search_backends = ["exa", "duckduckgo"]

[web_fetch]
timeout = 30
max_size_bytes = 5242880           # 5MB

# MCPサーバーは [[mcp.servers]] で追記（[mcp] に servers=[] と書かないこと）
[[mcp.servers]]
name = "filesystem"
transport = "stdio"                # "stdio" or "http"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
timeout = 30

# 複数サーバーは [[mcp.servers]] を繰り返す
[[mcp.servers]]
name = "playwright"
transport = "stdio"
command = "npx"
args = ["@playwright/mcp"]
timeout = 120
```

---

## 7. カスタムコマンド（F16）

よく使う操作をTOMLファイルで定義し、スラッシュコマンドとして呼び出せます。

### コマンド定義ファイルの作成

```bash
# プロジェクトローカルのコマンド雛形を生成
uv run myagent command init test-fix

# グローバルコマンドとして生成
uv run myagent command init deploy --global
```

生成先: `.myagent/commands/test-fix.toml`

### TOMLファイルの形式

```toml
name = "test-fix"
description = "テストを実行し、失敗を自動修正する"
prompt = """
以下の手順で作業してください:
1. `{{test_command}}` を実行する
2. 失敗したテストがあれば原因を分析する
3. コードを修正して再度テストを実行する
4. 全テストがパスするまで繰り返す
"""

[arguments]
test_command = { description = "テスト実行コマンド", default = "pytest" }
```

- `{{variable}}` — テンプレート変数（引数またはデフォルト値で置換される）
- `[arguments]` — 引数定義（`default` なしは必須引数）

### コマンドの優先順位

同名コマンドは **プロジェクトローカル** がグローバルより優先されます。

```
.myagent/commands/  ← 優先
~/.myagent/commands/
```

### コマンドの実行

```
# REPL内で実行
myagent> /test-fix
myagent> /test-fix --test_command "pytest -x tests/unit/"

# ワンショットで実行
uv run myagent --command test-fix --command-args '--test_command "pytest -x"'
```

### コマンド一覧の確認

```bash
uv run myagent command list
```

```
┌────────────────┬──────────────┬──────────────┬──────────────────────────┐
│ コマンド名      │ スコープ      │ 引数          │ 説明                     │
├────────────────┼──────────────┼──────────────┼──────────────────────────┤
│ /test-fix      │ プロジェクト  │ test_command  │ テストを実行し...         │
└────────────────┴──────────────┴──────────────┴──────────────────────────┘
* = 必須引数
```

---

## 8. スキル拡張（F14）

スキルは `SKILL.md` に記述した複合ワークフロー定義です。カスタムコマンドより複雑な処理に使います。

### スキルの雛形を生成

```bash
# プロジェクトスキルを作成
uv run myagent skill init my-workflow

# グローバルスキルを作成
uv run myagent skill init my-workflow --global
```

### スキルの呼び出し

REPL 内でスラッシュコマンドまたは自動キーワードマッチで起動します。

```
myagent> /my-workflow          # 明示的なスラッシュコマンド
myagent> ワークフローを実行して   # キーワードマッチによる自動起動
```

### スキル管理コマンド

```bash
# CLIサブコマンド
uv run myagent skill list
uv run myagent skill info <skill-name>
uv run myagent skill validate <path>
uv run myagent skill install <git-url-or-path>          # グローバル（~/.myagent/skills）
uv run myagent skill install <git-url-or-path> --local  # プロジェクトローカル
uv run myagent skill uninstall <skill-name>

# REPL内でも同様に実行可能
myagent> /skill list
myagent> /skill info my-workflow
myagent> /skill install https://github.com/example/skill-repo
myagent> /skill install https://github.com/example/skill-repo --local
```

> **インストール先**: デフォルトはグローバル（`~/.myagent/skills/`）です。`--local` を指定するとプロジェクトの `.myagent/skills/` にインストールされます。同名スキルはプロジェクトローカルが優先されます。

---

## 9. プラグイン管理（F15）

プラグインは複数のスキルをまとめたパッケージです。

### プラグイン管理コマンド

```bash
# CLIサブコマンド
uv run myagent plugin list
uv run myagent plugin install <git-url-or-path>   # ~/.myagent/plugins/cache/ にインストール
uv run myagent plugin uninstall <name>
uv run myagent plugin enable <name>
uv run myagent plugin disable <name>
uv run myagent plugin validate [path]

# REPL内でも同様に実行可能
myagent> /plugin list
myagent> /plugin install https://github.com/example/plugin-repo
myagent> /plugin enable my-plugin
```

> **インストール先**: プラグインは常に `~/.myagent/plugins/cache/`（ユーザースコープ）にインストールされます。CLIには `--scope` オプションがありますが、現在は `user` スコープのみ有効です。

### プラグインの有効化

インストールしただけでは有効になりません。`enable` コマンドで有効化するか、`config.toml` に記載します。

```toml
[plugin]
enabled_plugins = ["my-plugin", "another-plugin"]
```

---

## 10. MCPサーバー連携

MCP（Model Context Protocol）サーバーのツールをエージェントが使用できます。

### 設定（config.toml）

```toml
[[mcp.servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

[[mcp.servers]]
name = "my-api"
transport = "http"
url = "http://localhost:8080"
timeout = 60
```

> **注意**: `[mcp]` セクションに `servers = []` と書いた後に `[[mcp.servers]]` を追記するとTOMLパースエラーになります。`servers = []` の行は削除し、`[[mcp.servers]]` だけで定義してください。

### Playwright MCPの設定例

ブラウザ操作を行うPlaywright MCPサーバーを使う場合:

```bash
# Playwrightブラウザのインストール（初回のみ）
npx playwright install chromium
```

```toml
[[mcp.servers]]
name = "playwright"
transport = "stdio"
command = "npx"
args = ["@playwright/mcp"]
timeout = 120
```

接続すると `mcp_playwright_browser_navigate`、`mcp_playwright_browser_snapshot`、`mcp_playwright_browser_click` などのツールが使えるようになります。

#### Playwrightで継続操作する場合の注意

エージェントがブラウザ操作の提案を「完了しました」で終えた後に続けて操作する場合は、**ブラウザのコンテキストを明示**してください。

```
# NG（文脈が途切れ、ブラウザと無関係なツールが呼ばれることがある）
myagent> 「ホエイプロテイン」で絞り込み

# OK（Playwrightの文脈を明示する）
myagent> Playwrightで今開いているGoogleの検索バーに「ホエイプロテイン」を入力して再検索して
```

### 接続状態の確認

```bash
# CLIサブコマンド
uv run myagent mcp list        # サーバー一覧と接続状態
uv run myagent mcp test <name> # 指定サーバーへの接続テスト

# REPL内でも実行可能
myagent> /mcp list
myagent> /mcp test filesystem
```

---

## 11. LangSmithモニタリング

エージェントの実行トレース・LLM呼び出し・ツール実行をLangSmithで可視化できます。

### セットアップ

1. [https://smith.langchain.com](https://smith.langchain.com) でアカウントを作成し、APIキーを取得する
2. `.env` または `~/.myagent/.env` に以下を追加する:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=myagent    # LangSmith上のプロジェクト名（任意）
```

### 有効時の動作

起動時に以下のメッセージが表示されます:

```
作業ディレクトリ: /your/project/path
LangSmith トレース有効 (project: myagent)
```

各エージェント実行が LangSmith 上で1トレースとして記録され、以下が確認できます:

- LLM呼び出しの入出力・トークン数
- ツール実行の入力・出力
- 実行時間・コスト
- エラー発生箇所

### グローバル設定（全プロジェクト共通）

LangSmith は個人のAPIキーを使うため、`~/.myagent/.env` に書くのが推奨です。

```bash
# ~/.myagent/.env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=myagent
```

プロジェクトごとにプロジェクト名を変えたい場合は、プロジェクトの `.env` で上書きできます。

```bash
# プロジェクトの .env（~/.myagent/.env より優先される）
LANGCHAIN_PROJECT=my-specific-project
```

---

## 12. 開発者向け手順

### テストの実行

```bash
# 全ユニットテスト
uv run pytest

# 特定ディレクトリのテスト
uv run pytest tests/unit/commands/ -v

# カバレッジ付き実行
uv run pytest --cov=src --cov-report=html

# 統合テスト・E2Eテストを除外
uv run pytest --ignore=tests/integration --ignore=tests/e2e
```

### リントとフォーマット

```bash
# リントチェック
uv run ruff check src/

# 自動修正（importソートなど）
uv run ruff check --fix src/

# フォーマット
uv run ruff format src/
```

### 型チェック

```bash
uv run mypy src/
```

### 依存関係の更新

```bash
# ロックファイルを更新
uv lock --upgrade

# 依存関係を再インストール
uv sync
```

### 新機能の追加フロー

本プロジェクトは**スペック駆動開発**を採用しています。

```
1. docs/ に要件・設計ドキュメントを作成
2. .steering/<日付>-<機能名>/ にステアリングファイルを作成
   - requirements.md — 今回の要求内容
   - design.md       — 実装アプローチ
   - tasklist.md     — タスクリスト
3. tasklist.md に従って実装
4. テスト・lint・型チェックを通す
5. docs/ の該当ドキュメントを更新
```

Claude Code を使う場合は `/add-feature <機能名>` スキルで自動実行されます。

---

## 13. トラブルシューティング

### OneDrive上でのインストールに失敗する

リポジトリが OneDrive フォルダ内にある場合、`uv tool install .` がハードリンクの制限で失敗することがあります。

```
error: Failed to install: ...
  Caused by: failed to hardlink file ... クラウド操作は、互換性のないハードリンクのファイルでは実行できません。
```

`--link-mode=copy` を指定してコピーモードでインストールします:

```bash
uv tool install --link-mode=copy .
```

毎回指定が面倒な場合は環境変数で永続化できます:

```bash
# .env または ~/.bashrc / ~/.zshrc に追加
UV_LINK_MODE=copy
```

### APIキーが認識されない

```bash
# 環境変数が読まれているか確認
echo $OPENAI_API_KEY

# .env が正しい場所にあるか確認
ls -la .env

# 現在の設定を確認
uv run myagent config
```

キーが読まれない場合は `~/.myagent/.env` にも設定を追加してください。

### LLMのフォールバックが発生する

プライマリプロバイダがエラーの場合、フォールバックプロバイダに自動切替します。

```bash
# フォールバック先を変更
uv run myagent set-config --fallback-provider gemini --fallback-model gemini-2.5-flash
```

### コンテキストが長くなりすぎる

`/clear` コマンドで会話履歴をリセットします。

```
myagent> /clear
```

または `context_window_tokens` を大きくすることで圧縮タイミングを遅らせられます（config.toml）。

### カスタムコマンドが見つからない

```bash
# コマンドが正しくロードされているか確認
uv run myagent command list

# コマンドディレクトリを確認
ls .myagent/commands/
```

**よくある原因**:
- ファイル名と `name` フィールドが一致していない
- `name` フィールドの命名規則違反（小文字英数字とハイフンのみ）
- `prompt` フィールドが未定義

### スキルが自動マッチしない

スキルの `description` フィールドに関連キーワードを充実させてください（`SKILL.md` のフロントマター）。

### MCPサーバーの設定でパースエラーが出る

```
Cannot mutate immutable namespace ('mcp', 'servers')
```

このエラーは `[mcp]` セクション内に `servers = []` と書いた後、`[[mcp.servers]]` で追記した場合に発生します。

**修正**: `servers = []` の行を削除します。

```toml
# NG
[mcp]
servers = []

[[mcp.servers]]
name = "playwright"
...

# OK
[mcp]

[[mcp.servers]]
name = "playwright"
...
```

### MCPツールで "There is no current event loop" エラーが出る

古いバージョンで発生する問題です。`graph.py` の `tool_node_wrapper` が同期関数だった場合に起きます。最新版では `async def` に修正済みです。

### スキルをインストールしたが `/skill list` に表示されない

インストール先とスキルの検索先が一致しているか確認してください。

- `/skill install`（デフォルト）: `~/.myagent/skills/` にインストール
- `/skill install --local`: `<カレントディレクトリ>/.myagent/skills/` にインストール

`/skill list` はグローバル（`~/.myagent/skills/`）とプロジェクトローカル（`.myagent/skills/`）の両方を検索します。`config.toml` の `global_skills_dir` を設定している場合はその場所も確認してください。

### LangSmithにトレースが記録されない

1. `LANGCHAIN_TRACING_V2=true` が設定されているか確認
2. 起動時に「LangSmith トレース有効」メッセージが表示されているか確認
3. `LANGCHAIN_API_KEY` が正しいか確認（`ls__` で始まるキー）
4. `.env` が起動ディレクトリ（または `~/.myagent/.env`）に存在するか確認

---

## 14. ディレクトリ構造

```
MyCode/
├── src/myagent/
│   ├── main.py                # エントリーポイント
│   ├── cli/
│   │   ├── app.py             # REPL・ワンショット実行
│   │   ├── commands.py        # Click コマンド定義
│   │   ├── slash_router.py    # REPL内管理コマンド（/plugin, /skill 等）
│   │   └── display.py         # Rich 表示制御
│   ├── agent/
│   │   ├── graph.py           # LangGraph ステートマシン（AgentRunner）
│   │   ├── planner.py         # タスク分解・依存関係解析
│   │   ├── orchestrator.py    # マルチエージェント並列実行
│   │   ├── executor.py        # ツール実行制御・確認フロー
│   │   ├── critic.py          # 結果評価・エラー繰り返し検知
│   │   ├── prompt_manager.py  # タスク種別ごとのプロンプト管理
│   │   ├── tool_validator.py  # ツール呼び出し前パラメータ検証
│   │   ├── metrics.py         # セッションメトリクス追跡
│   │   ├── events.py          # エージェントイベント定義
│   │   ├── state.py           # LangGraph ステート定義
│   │   └── prompts/           # プロンプトテンプレートファイル
│   │       ├── base.txt
│   │       ├── coding.txt
│   │       ├── refactoring.txt
│   │       └── research.txt
│   ├── llm/
│   │   └── router.py          # LLMプロバイダ切替・フォールバック
│   ├── tools/
│   │   ├── registry.py        # ツール登録・管理
│   │   ├── file_tools.py      # ファイル操作
│   │   ├── shell_tools.py     # シェル実行
│   │   ├── web_tools.py       # Web検索・取得（Exa / DuckDuckGo）
│   │   └── mcp_tools.py       # MCPサーバー統合
│   ├── commands/              # カスタムコマンド（F16）
│   │   ├── models.py          # データモデル
│   │   ├── loader.py          # TOMLパース
│   │   └── manager.py         # コマンド管理
│   ├── skills/                # スキル拡張（F14）
│   │   ├── models.py          # データモデル
│   │   ├── loader.py          # SKILL.md パース
│   │   ├── installer.py       # スキルインストール
│   │   └── manager.py         # スキル管理
│   ├── plugins/               # プラグイン管理（F15）
│   │   ├── models.py          # データモデル
│   │   ├── loader.py          # プラグインロード
│   │   ├── installer.py       # プラグインインストール
│   │   └── manager.py         # プラグイン管理
│   └── infra/
│       ├── config.py          # 設定管理（TOML + 環境変数）
│       ├── context.py         # コンテキスト圧縮・優先度管理
│       └── errors.py          # カスタム例外
│
├── tests/                     # テストコード
│   └── unit/                  # ユニットテスト（pytest）
│
├── docs/                      # 永続ドキュメント
│   ├── product-requirements.md
│   ├── functional-design.md
│   ├── architecture.md
│   ├── development-guidelines.md
│   ├── references/            # 技術調査・参考資料
│   └── MANUAL.md              # 本ファイル
│
├── .steering/                 # 作業単位のステアリングファイル（gitignore対象）
├── .myagent/                  # プロジェクトローカル設定（gitignore対象）
│   ├── commands/              # カスタムコマンド定義（TOML）
│   └── skills/                # プロジェクトスキル（SKILL.md）
│
├── .claude/                   # Claude Code設定
│   ├── skills/                # Claude Codeスキル
│   └── settings.json          # Claude Code設定
│
├── .env                       # APIキー（gitignore対象）
├── .env.example               # APIキーのテンプレート
├── pyproject.toml             # プロジェクト設定・依存関係
└── uv.lock                    # 依存関係ロックファイル
```

---

## 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| `docs/product-requirements.md` | プロダクト要求定義書（全機能の受け入れ条件） |
| `docs/functional-design.md` | 機能設計書（コンポーネント設計・データフロー） |
| `docs/architecture.md` | 技術仕様書（アーキテクチャパターン・依存関係） |
| `docs/development-guidelines.md` | 開発ガイドライン（コーディング規約） |
| `docs/glossary.md` | ユビキタス言語定義 |
