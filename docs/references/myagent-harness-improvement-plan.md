# myagent 改善計画: Anthropicハーネス設計ベストプラクティス適用

## Context

Anthropicのエンジニアリングブログ記事「Harness design for long-running application development」
（`docs/references/Harness design for long-running application development _ Anthropic.mhtml`）のベストプラクティスを参照し、myagentの現状とのGAPを分析。生成品質向上・評価フィードバックループの強化・スプリント契約の導入を目的とする。

---

## ベストプラクティスとGAP分析

| # | ベストプラクティス | myagent現状 | GAP評価 |
|---|---|---|---|
| BP1 | **生成器/評価器の明確な分離**（独立コンテキスト） | `Critic` はループ/エラー検知のみ。品質評価なし | 🔴 大 |
| BP2 | **スプリント契約**（完了定義を事前合意） | `SubTask` に `acceptance_criteria` フィールドなし | 🔴 大 |
| BP3 | **評価エージェントへのPlaywright MCP提供** | MCP接続基盤は存在するが評価用途への転用設計がない | 🟡 中 |
| BP4 | **戦略的反復判断**（スコアトレンドで洗練 vs 方向転換） | ルールベース（N回連続のみ）で評価スコアの概念なし | 🟡 中 |
| BP5 | **モデル進化に伴うハーネスの段階的簡素化** | 機能の有効/無効フラグが存在しない | 🟢 小 |
| BP6 | **具体的なエラー報告**（動作確認付き） | 汎用的な「別アプローチを試せ」メッセージのみ | 🟡 中 |
| BP7 | **評価プロンプトの言語設計**（主観→客観的基準） | 評価専用プロンプトテンプレートが存在しない | 🔴 大 |

**特記**: `events.py` に `evaluate_start/evaluate_end` イベントが定義されているが、一度も発火されていない（デッドコード）。

---

## 改善提案

### フェーズ1（優先度: 高）

#### 改善A: `evaluation.py` の新設と `Critic` の品質評価機能拡張

**目的**: BP1・BP7 — 品質スコアリング基盤の確立

**対象ファイル**:
- `src/myagent/agent/evaluation.py`（新規）
- `src/myagent/agent/critic.py`
- `src/myagent/agent/prompts/evaluation.txt`（新規）

**方針**:
1. 循環インポートを避けるため `EvaluationResult` 型を `evaluation.py` に独立定義
   ```python
   @dataclass
   class EvaluationResult:
       score: int                   # 0-100
       passed_criteria: list[str]
       failed_criteria: list[str]
       suggestion: str
   ```
2. `Critic` に `async evaluate_output(output, criteria, model) -> EvaluationResult` を追加
3. 評価プロンプト `evaluation.txt` の言語設計原則:
   - 「生成したのは別のエージェントです。独立した評価者として客観的に判断してください」の明示
   - 主観的表現の排除（「良い」→「要件Xを満たすか Yes/No」）
   - JSON出力を強制（`score`, `passed`, `failed`, `suggestion`）

---

#### 改善B: `SubTask` への受け入れ基準追加（スプリント契約の基盤）

**目的**: BP2 — 完了定義の事前合意

**対象ファイル**:
- `src/myagent/agent/state.py`
- `src/myagent/agent/planner.py`

**方針**:
1. `state.py` の `SubTask` に `acceptance_criteria: list[str] = field(default_factory=list)` を追加
2. `planner.py` の `_PLANNER_DEPENDENCY_PROMPT` の JSON スキーマに `acceptance_criteria` 配列を追加
   ```json
   {
     "id": "t1",
     "description": "...",
     "acceptance_criteria": [
       "単体テストがパスする",
       "型ヒントが全メソッドに付与されている"
     ]
   }
   ```

---

#### 改善C: 評価イベントの実際の発火

**目的**: BP1 — 評価進捗の可視化

**対象ファイル**:
- `src/myagent/agent/events.py`
- `src/myagent/agent/orchestrator.py`
- `src/myagent/cli/display.py`

**方針**:
1. `AgentEvent` に `evaluate_start(task_id, criteria_count)` / `evaluate_end(task_id, score, passed_count, failed_count)` のファクトリメソッドを追加
2. `Orchestrator._run_worker()` 完了後: `acceptance_criteria` があれば改善Aの `evaluate_output()` を呼び出し、両イベントを発火
3. `display.py` の `handle_event()` でこれらを受け取りコンソール表示

---

### フェーズ2（優先度: 中）

#### 改善D: 評価専用ワーカーの設計（独立コンテキスト）

**目的**: BP1・BP3 — 生成/評価コンテキストの完全分離

**対象ファイル**:
- `src/myagent/agent/orchestrator.py`

**方針**:
- 既存の `_create_worker()` を参考に `_create_evaluator_worker()` を追加
- 評価エージェントには **読み取り専用ツール（read_file, grep_search, glob_search）+ Playwright MCP（設定時のみ）** を提供
- 生成エージェントのツールセットとは分離する

---

#### 改善E: スコアトレンドによる戦略的判断の強化

**目的**: BP4 — ルールベースから評価スコア駆動への移行

**対象ファイル**:
- `src/myagent/agent/state.py`（`evaluation_history` フィールド追加）
- `src/myagent/agent/critic.py`（`build_strategy_message()` 追加）
- `src/myagent/agent/graph.py`（`agent_node` の判断ロジック拡張）

**方針**:
- `AgentState` に `evaluation_history: list[EvaluationResult]` を追加（`total=False` なので後方互換）
- `Critic.build_strategy_message(history)` がスコアトレンドをLLMに判断させる:
  - 向上中 → 「現在の方向性を継続し洗練させてください」
  - 低下/停滞 → 「全く異なるアプローチを試みてください」

---

#### 改善F: スキルへの受け入れ基準宣言機能

**目的**: BP2 — スプリント契約をスキルシステムに適用

**対象ファイル**:
- `src/myagent/skills/models.py`
- `src/myagent/skills/loader.py`
- `src/myagent/cli/app.py`

**方針**:
- `SkillMetadata` に `acceptance_criteria: list[str]` フィールドを追加
- `loader.py` で SKILL.md の `## 受け入れ基準` セクションをパース
- `app.py` のスキル自動続行フローで、基準を持つスキルは実行後に評価を実施

---

### フェーズ3（優先度: 低）

#### 改善G: ハーネス機能の段階的有効化フラグ

**目的**: BP5 — モデル進化に合わせた簡素化対応

**対象ファイル**: `src/myagent/infra/config.py`

**追加フィールド**:
```python
# AgentConfig 内に追加
enable_sprint_evaluation: bool = False   # スプリント契約評価
enable_quality_scoring: bool = False     # 品質スコアリング
evaluation_threshold: int = 70           # 再試行トリガー閾値
max_evaluation_iterations: int = 5      # 評価ループ上限
```

#### 改善H: Critic のエラー診断具体化

**目的**: BP6 — ツール固有の診断ヒント追加

**対象ファイル**: `src/myagent/agent/critic.py`

**方針**: `build_recovery_message()` にツール別診断ヒント辞書を追加。`edit_file` 失敗時は「ファイルの存在確認を先に行ったか？」等の具体的質問を含める。

---

## 実装順序とファイル変更一覧

```
フェーズ1（基盤）:
  新規: src/myagent/agent/evaluation.py         # EvaluationResult 型定義
  新規: src/myagent/agent/prompts/evaluation.txt # 評価プロンプトテンプレート
  修正: src/myagent/agent/critic.py              # evaluate_output() 追加
  修正: src/myagent/agent/state.py               # SubTask.acceptance_criteria
  修正: src/myagent/agent/planner.py             # プロンプト拡張
  修正: src/myagent/agent/events.py              # evaluate_* ファクトリ追加
  修正: src/myagent/agent/orchestrator.py        # 評価呼び出し + イベント発火
  修正: src/myagent/cli/display.py               # 評価イベント表示

フェーズ2（拡張）:
  修正: src/myagent/agent/orchestrator.py        # _create_evaluator_worker()
  修正: src/myagent/agent/state.py               # evaluation_history フィールド
  修正: src/myagent/agent/critic.py              # build_strategy_message()
  修正: src/myagent/agent/graph.py               # スコアトレンド判断ロジック
  修正: src/myagent/skills/models.py             # SkillMetadata.acceptance_criteria
  修正: src/myagent/skills/loader.py             # 受け入れ基準パース
  修正: src/myagent/cli/app.py                   # スキル評価フィードバック注入

フェーズ3（維持性）:
  修正: src/myagent/infra/config.py              # 有効化フラグ追加
  修正: src/myagent/agent/critic.py              # エラー診断具体化
```

---

## 検証方法

1. **ユニットテスト**:
   - `tests/unit/agent/test_critic.py` に `evaluate_output()` のテストを追加
   - `tests/unit/agent/test_planner.py` に `acceptance_criteria` 生成のテストを追加
   - `uv run pytest tests/` — 全テストパス確認

2. **統合テスト（手動）**:
   - `uv run myagent` で REPL を起動
   - `/techlearn Claude Code ハンズオン作成して` を実行
   - コンソールに `evaluate_start` / `evaluate_end` イベントが表示されることを確認
   - 評価スコアと改善指摘がログに記録されることを確認

3. **リント**:
   - `uv run ruff check src/myagent/agent/evaluation.py src/myagent/agent/critic.py`

4. **型チェック**（任意）:
   - `uv run mypy src/myagent/agent/evaluation.py`

---

## 設計上の重要な決断

### なぜ `evaluation.py` を独立させるか

`EvaluationResult` を `critic.py` に置くと `state.py` → `critic.py` の循環インポートが発生する（`AgentState` が `EvaluationResult` を参照するため）。`evaluation.py` を独立させることで両者から安全にインポートできる。

### なぜ評価機能をデフォルト無効（フェーズ3）にするか

Anthropicの記事が強調する「モデルが進化すれば不要な複雑性は除去すべき」という原則を実装段階から組み込む。フラグ無効時は従来通りの動作を保証し、テスト容易性も維持する。

### 既存の強みを活かす点

- `Orchestrator._create_worker()` の独立 `AgentRunner` 生成パターン → 評価専用ワーカーに転用
- `MCPManager` の汎用接続基盤 → Playwright MCP を評価エージェントへ選択的提供
- `events.py` の `evaluate_start/evaluate_end` 定義 → フェーズ1で実際に発火させる
