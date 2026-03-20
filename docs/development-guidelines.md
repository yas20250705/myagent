# 開発ガイドライン (Development Guidelines)

## コーディング規約

### 命名規則

#### 変数・関数

```python
# ✅ 良い例
user_instruction = "テストを実行して"
tool_call_history: list[ToolCall] = []
is_blocked = check_blocked_command(command)

def parse_tool_output(raw_output: str) -> ToolResult: ...
def build_agent_graph() -> StateGraph: ...
def detect_infinite_loop(history: list[ToolCall]) -> bool: ...

# ❌ 悪い例
instr = "テストを実行して"
data: list = []

def parse(s: str) -> object: ...
def build() -> object: ...
```

**原則**:
- 変数: snake_case、名詞または名詞句
- 関数: snake_case、動詞で始める
- 定数: UPPER_SNAKE_CASE
- Boolean: `is_`, `has_`, `should_`, `can_` で始める

#### クラス

```python
# クラス: PascalCase、名詞
class AgentCore: ...
class LLMRouter: ...
class ToolRegistry: ...

# Protocol（インターフェース相当）
from typing import Protocol

class LLMProvider(Protocol):
    async def invoke(self, messages: list[dict]) -> LLMResponse: ...
    async def stream(self, messages: list[dict]) -> AsyncIterator[str]: ...

# 型エイリアス: PascalCase
AgentPhase = Literal["planning", "executing", "observing", "evaluating", "completed", "failed"]
EventType = Literal["stream_token", "tool_start", "tool_end", "confirm_request"]
```

#### 定数

```python
# UPPER_SNAKE_CASE
MAX_ITERATIONS = 25
RETRY_BASE_DELAY = 1.0
CONTEXT_COMPRESSION_THRESHOLD = 0.8  # コンテキストウィンドウの80%

BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"mkfs\.",
    r"\bdd\b.*of=/dev/",
]

SENSITIVE_FILE_PATTERNS = [
    ".env", ".env.*",
    "*credentials*", "*secret*",
    "*.pem", "*.key",
]
```

### コードフォーマット

**インデント**: 4スペース

**行の長さ**: 最大88文字（ruff デフォルト）

**import順序**: ruff が自動整理（標準ライブラリ → サードパーティ → ローカル）

```python
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph

from myagent.agent.state import AgentState
from myagent.infra.config import AppConfig
```

### コメント規約

**Docstring（Google Style）**:
```python
async def invoke(
    self,
    messages: list[dict[str, str]],
    tools: list[dict] | None = None,
) -> LLMResponse:
    """LLMを呼び出す。失敗時はフォールバックプロバイダに切替。

    Args:
        messages: 会話履歴（role, content形式）
        tools: ツール定義のJSON Schemaリスト

    Returns:
        LLMからの応答

    Raises:
        LLMError: 全プロバイダで失敗した場合
    """
```

**インラインコメント**:
```python
# ✅ 良い例: なぜそうするかを説明
# symlinkを解決してプロジェクトルート外へのアクセスを防ぐ
real_path = os.path.realpath(path)

# ❌ 悪い例: 何をしているか（コードを見れば分かる）
# パスを正規化する
real_path = os.path.realpath(path)
```

### エラーハンドリング

**カスタム例外クラス**:
```python
class MyAgentError(Exception):
    """MyAgent共通の基底例外"""

class LLMError(MyAgentError):
    """LLM API呼び出しの失敗"""
    def __init__(self, message: str, provider: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.__cause__ = cause

class ToolExecutionError(MyAgentError):
    """ツール実行の失敗"""
    def __init__(self, message: str, tool_name: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.__cause__ = cause

class SecurityError(MyAgentError):
    """セキュリティ制約の違反"""

class ConfigError(MyAgentError):
    """設定の読み込み・検証エラー"""
```

**エラーハンドリングパターン**:
```python
# ✅ 良い例: 適切なエラー処理と伝播
async def invoke(self, messages: list[dict]) -> LLMResponse:
    try:
        return await self._primary.invoke(messages)
    except Exception as e:
        logger.warning(f"プライマリプロバイダ失敗: {e}")
        try:
            return await self._fallback.invoke(messages)
        except Exception as fallback_error:
            raise LLMError(
                "全プロバイダで失敗しました",
                provider="all",
            ) from fallback_error

# ❌ 悪い例: エラーを無視
async def invoke(self, messages: list[dict]) -> LLMResponse | None:
    try:
        return await self._primary.invoke(messages)
    except Exception:
        return None  # エラー情報が失われる
```

### 非同期処理

```python
# ✅ 良い例: 独立したツール呼び出しの並列実行
async def execute_parallel_tools(
    tools: list[tuple[str, dict]],
) -> list[str]:
    return await asyncio.gather(
        *[registry.execute(name, input_data) for name, input_data in tools]
    )

# ✅ ストリーミング処理
async def stream_response(self, messages: list[dict]) -> AsyncIterator[str]:
    async for chunk in self._provider.stream(messages):
        yield chunk.content
```

### 型ヒント

```python
# ✅ 組み込み型を使用（Python 3.10+）
def process_messages(messages: list[dict[str, str]]) -> dict[str, Any]: ...

# ✅ Union型は | 記法
def find_tool(name: str) -> BaseTool | None: ...

# ✅ Literalで列挙値を表現
ConfirmationLevel = Literal["strict", "normal", "autonomous"]

# ❌ 旧スタイル
from typing import List, Dict, Optional, Union
def process_messages(messages: List[Dict[str, str]]) -> Dict[str, Any]: ...
```

---

## Git運用ルール

### ブランチ戦略

**ブランチ構成**:
```
main (本番リリース済みの安定版)
└── develop (開発・統合)
    ├── feature/cli-repl          # 新機能開発
    ├── feature/llm-router
    ├── fix/shell-timeout         # バグ修正
    └── refactor/tool-registry    # リファクタリング
```

**運用ルール**:
- **main**: 本番リリース済みの安定版。タグでバージョン管理
- **develop**: 次期リリースに向けた最新の開発コード。CIで自動テスト実施
- **feature/\*、fix/\*、refactor/\***: developから分岐し、PRでdevelopへマージ
- **直接コミット禁止**: 全ブランチでPRレビューを必須とする
- **マージ方針**: feature→develop は squash merge、develop→main は merge commit

### コミットメッセージ規約

**フォーマット（Conventional Commits）**:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type一覧**:
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `style`: コードフォーマット
- `refactor`: リファクタリング
- `perf`: パフォーマンス改善
- `test`: テスト追加・修正
- `chore`: ビルド、依存関係更新等

**Scope一覧（本プロジェクト）**:
- `cli`: CLIレイヤー
- `agent`: エージェントレイヤー
- `llm`: LLMレイヤー
- `tools`: ツールレイヤー
- `infra`: インフラレイヤー
- `config`: 設定管理
- `deps`: 依存関係

**例**:
```
feat(agent): Plan-Execute-Criticループを実装

LangGraphのStateGraphを使用してエージェントの思考ループを実装。
- Plannerノード: ユーザー指示をサブタスクに分解
- Executorノード: ツール呼び出しと結果収集
- Criticノード: 結果評価と再試行判断
- 最大25イテレーションで無限ループを防止

Closes #15
```

### プルリクエストプロセス

**作成前のチェック**:
- [ ] `uv run ruff check .` でLintエラーがない
- [ ] `uv run ruff format --check .` でフォーマット差分がない
- [ ] `uv run mypy src` で型チェックがパス
- [ ] `uv run pytest` で全テストがパス
- [ ] 競合が解決されている

**PRテンプレート**:
```markdown
## 変更の種類
- [ ] 新機能 (feat)
- [ ] バグ修正 (fix)
- [ ] リファクタリング (refactor)
- [ ] ドキュメント (docs)
- [ ] その他 (chore)

## 変更内容
### 何を変更したか
[簡潔な説明]

### なぜ変更したか
[背景・理由]

### どのように変更したか
- [変更点1]
- [変更点2]

## テスト
- [ ] ユニットテスト追加
- [ ] 統合テスト追加
- [ ] 手動テスト実施

## 関連Issue
Closes #[番号]
```

**PRサイズの目安**:
- 変更ファイル数: 10ファイル以内
- 変更行数: 300行以内
- 大規模な変更は複数のPRに分割

---

## テスト戦略

### テストの種類と目標比率

```
       /\
      /E2E\       10% (遅い、実LLM API使用)
     /------\
    / 統合   \     20%
   /----------\
  / ユニット   \   70% (速い、モック使用)
 /--------------\
```

**カバレッジ目標**: 80%以上

### ユニットテスト

**対象**: 個別の関数・クラス（LLM呼び出しはモック）

```python
class TestPlanner:
    def test_単純な指示をサブタスクに分解できる(self) -> None:
        # Given
        mock_llm = MagicMock(spec=LLMRouter)
        mock_llm.invoke.return_value = LLMResponse(
            content='[{"description": "テスト実行"}, {"description": "結果確認"}]'
        )
        planner = Planner(llm=mock_llm)
        state = AgentState(messages=[{"role": "user", "content": "テストを実行して"}])

        # When
        result = planner.plan(state)

        # Then
        assert len(result.plan) == 2
        assert result.plan[0].description == "テスト実行"
        assert result.phase == "executing"

    def test_不正なLLM出力でリプランする(self) -> None:
        # Given
        mock_llm = MagicMock(spec=LLMRouter)
        mock_llm.invoke.return_value = LLMResponse(content="不正なJSON")
        planner = Planner(llm=mock_llm)
        state = AgentState(messages=[{"role": "user", "content": "何かして"}])

        # When
        result = planner.plan(state)

        # Then
        assert result.error_count == 1
```

### 統合テスト

**対象**: 複数コンポーネントの連携（LLMはモック、ツールは実実装）

```python
class TestAgentLoop:
    def test_ファイル読み込みタスクを完了できる(self, tmp_path: Path) -> None:
        # Given: テスト用ファイルを作成
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # Agent構築（LLMモック、ツールは実実装）
        agent = build_test_agent(mock_llm_responses=[...])

        # When
        result = asyncio.run(agent.run("test.pyの内容を読んで"))

        # Then
        assert result.phase == "completed"
        assert "hello" in result.tool_history[0].output_data
```

### E2Eテスト

**対象**: CLIからのエンドツーエンド（実LLM API使用、CI環境ではスキップ）

```python
@pytest.mark.e2e
class TestInteractiveMode:
    def test_ワンショットでファイル内容を返す(self) -> None:
        result = subprocess.run(
            ["myagent", "READMEの内容を教えて"],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0
        assert "README" in result.stdout or "readme" in result.stdout.lower()
```

### テスト命名規則

```python
# ✅ 良い例: 日本語で条件と期待結果を明示
def test_空のコマンドでエラーを返す(self) -> None: ...
def test_危険コマンドをブロックする(self) -> None: ...
def test_プロバイダ障害時にフォールバックする(self) -> None: ...

# ❌ 悪い例
def test1(self) -> None: ...
def test_it_works(self) -> None: ...
```

### モック・スタブの使用

**原則**:
- LLM API呼び出し: 常にモック化（ユニット・統合テスト）
- ファイルシステム: `tmp_path` フィクスチャを使用
- シェルコマンド: 安全なコマンドのみ実実行、危険なものはモック
- Git操作: テスト用リポジトリを `tmp_path` に作成

```python
# conftest.py - 共通フィクスチャ
@pytest.fixture
def mock_llm_router() -> MagicMock:
    router = MagicMock(spec=LLMRouter)
    router.invoke.return_value = LLMResponse(content="OK")
    return router

@pytest.fixture
def tool_registry(tmp_path: Path) -> ToolRegistry:
    registry = ToolRegistry(project_root=str(tmp_path))
    registry.register_defaults()
    return registry
```

---

## コードレビュー基準

### レビューポイント

**機能性**:
- [ ] PRDの要件を満たしているか
- [ ] エッジケースが考慮されているか（空入力、大量データ、タイムアウト等）
- [ ] エラーハンドリングが適切か

**セキュリティ**:
- [ ] コマンドインジェクションの可能性がないか
- [ ] ファイルアクセスがプロジェクトルートに制限されているか
- [ ] APIキーがログに出力されていないか
- [ ] 機密ファイルの読み取り時に警告があるか

**可読性**:
- [ ] 命名が明確で一貫しているか
- [ ] 複雑なロジックにコメントがあるか
- [ ] 関数が単一の責務を持っているか

**パフォーマンス**:
- [ ] 不要なLLM呼び出しがないか
- [ ] ツール出力のトランケーションが適切か
- [ ] asyncioの並列実行が活用されているか

**アーキテクチャ**:
- [ ] レイヤー間の依存ルールに違反していないか
- [ ] 循環依存がないか

### レビューコメントの優先度

- `[必須]`: 修正必須（セキュリティ、バグ、アーキテクチャ違反）
- `[推奨]`: 修正推奨（パフォーマンス、可読性）
- `[提案]`: 検討してほしい（代替案、改善案）
- `[質問]`: 理解のための質問

---

## 開発環境セットアップ

### 必要なツール

| ツール | バージョン | インストール方法 |
|--------|-----------|-----------------|
| Python | 3.12+ | devcontainer / pyenv |
| uv | 最新版 | `pip install uv` |
| Git | 最新版 | OS標準 / devcontainer |

### セットアップ手順

```bash
# 1. リポジトリのクローン
git clone [URL]
cd myagent

# 2. 依存関係のインストール
uv sync

# 3. 環境変数の設定
cp .env.example .env
# .envファイルにAPIキーを設定:
#   OPENAI_API_KEY=sk-...
#   GOOGLE_API_KEY=...

# 4. 品質チェック
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

### 日常の開発コマンド

```bash
# リント + フォーマット
uv run ruff check . --fix
uv run ruff format .

# 型チェック
uv run mypy src

# テスト実行
uv run pytest                          # 全テスト
uv run pytest tests/unit/              # ユニットテストのみ
uv run pytest -m "not e2e"             # E2E以外
uv run pytest --cov=src --cov-report=html  # カバレッジ付き

# アプリケーション実行
uv run myagent                         # 対話モード
uv run myagent "指示内容"              # ワンショット
```

---

## 自動化

### CI/CD (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install uv && uv sync
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest -m "not e2e" --cov=src --cov-report=xml
```

### Pre-commit フック

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

```bash
# インストール
uv add --dev pre-commit
uv run pre-commit install
```
