# Claude Code vs myagent: AIエージェント・ワークフロー差分分析

## 1. エグゼクティブサマリー

Claude Codeの回答精度がmyagentより高い主要因は以下の3点に集約される:

1. **システムプロンプトの情報密度と具体性の圧倒的な差** — Claude Codeは約15,000語の超詳細なシステムプロンプトを使用
2. **ツール定義の精緻さ** — 各ツールに詳細なdescription、使い分けルール、アンチパターンを明記
3. **行動制約の明示性** — 「やるべきこと」「やってはいけないこと」を具体例付きで網羅的に指示

---

## 2. システムプロンプト構造の比較

### 2.1 myagentのシステムプロンプト

```
base.txt (約30行)
├── 役割定義: 「高度なAIコーディングアシスタント」（1文）
├── 基本行動: 「ツールを使って作業を完了」（2文）
├── 情報正確性ルール (websearch優先)
└── task_type別テンプレート (coding/research/refactoring, 各10-15行)

動的注入:
├── 作業ディレクトリ (3行)
├── skills_context (スキルカタログ)
└── project_index (ファイルツリー)
```

**合計: 約50-80行**

### 2.2 Claude Codeのシステムプロンプト

```
メインプロンプト (約800行以上)
├── Identity & Role (詳細な自己定義)
├── Tool Usage Rules (各ツールごとの詳細な使い分けルール)
│   ├── Read vs cat/head/tail の使い分け
│   ├── Edit vs sed/awk の使い分け
│   ├── Grep vs grep/rg の使い分け
│   ├── Glob vs find/ls の使い分け
│   ├── Write vs echo の使い分け
│   └── Bash: 専用ツールが使えない場合のみ
├── Doing Tasks (タスク実行の詳細ガイドライン)
│   ├── コード読解してから変更する
│   ├── Over-engineeringの禁止（具体例付き）
│   ├── セキュリティ脆弱性を避ける
│   ├── 後方互換ハックの禁止
│   └── ファイル作成は最小限
├── Executing Actions with Care
│   ├── 可逆性とblast radiusの考慮
│   ├── 危険操作の具体例リスト
│   ├── ユーザー確認が必要なケース
│   └── 破壊的操作の回避
├── Git Operations (詳細なgitワークフロー)
│   ├── コミットメッセージ作成手順 (8ステップ)
│   ├── PR作成手順 (6ステップ)
│   └── Co-Authored-Byの書式
├── Tone and Style
│   ├── 簡潔さの要求
│   ├── file_path:line_number 形式
│   └── emoji使用ルール
├── Output Efficiency
│   ├── 冗長な説明の禁止
│   ├── ユーザー発言の繰り返し禁止
│   └── フォーカスすべき出力内容
├── Auto Memory System (長期記憶)
│   ├── user/feedback/project/reference の4種
│   ├── 保存・取得・更新のルール
│   └── 記憶の鮮度管理
├── Agent System (サブエージェント)
│   ├── 9種のエージェントタイプ
│   ├── foreground/background 使い分け
│   └── isolation (worktree) モード
├── Skill System
│   ├── スキル一覧と用途
│   └── トリガー条件
└── Environment Context
    ├── OS/Shell/Platform
    ├── git status
    ├── current date
    └── model info

動的注入:
├── CLAUDE.md (プロジェクト固有の指示)
├── system-reminder (スキル内容、ツール定義等)
└── gitStatus (現在のブランチ状態)
```

**合計: 約15,000語（推定）**

### 2.3 差分のインパクト

| 観点 | myagent | Claude Code |
|------|---------|-------------|
| プロンプト量 | ~80行 | ~800行以上 |
| ツール使い分けルール | なし | 各ツールペアごとに明記 |
| アンチパターン | なし | 具体例付きで網羅 |
| 出力スタイル指示 | なし | 詳細（簡潔さ、形式、トーン） |
| 安全性ガイドライン | なし | 可逆性/blast radius/確認フロー |
| git操作手順 | なし | コミット/PR作成の完全手順 |
| 長期記憶 | なし | 4種の記憶タイプと管理ルール |

---

## 3. ツール定義の精度比較

### 3.1 myagentのツール定義

myagentのツールは `BaseTool` サブクラスとして定義され、`name` と `description` を持つ。descriptionは短い1-2文。

```python
# 例: ReadFileTool
name = "read_file"
description = "ファイルを読み込みます。"
```

`args_schema`は Pydantic モデルで定義されるが、フィールドの説明は最小限。

### 3.2 Claude Codeのツール定義

Claude Codeの各ツールは **数百語のdescription** を持つ。例:

```
Read tool:
- 絶対パスが必須
- デフォルトで2000行、offset/limitでの部分読み込み
- 画像/PDF/Jupyterの読み込み対応
- ディレクトリは読めない（ls使用を案内）
- 並列呼び出しの推奨
- スクリーンショット対応の明記
```

```
Bash tool:
- 専用ツールがある場合はBashを使わない（Read/Edit/Write/Grep/Glob）
- cdを避けて絶対パスを使う
- descriptionにコマンドの説明を書く（簡潔に）
- タイムアウト設定
- バックグラウンド実行
- git操作の安全プロトコル
```

```
Edit tool:
- 事前にReadが必須
- インデント保持のルール
- old_stringのユニーク性
- replace_allの用途
- emoji使用ルール
```

### 3.3 差分のインパクト

**myagentの問題**: LLMがツールの使い方を「推測」する必要がある。descriptionが短いため、パラメータの使い分け、エッジケース、制約を知らずに呼び出す。

**Claude Codeの優位性**: ツールのdescription自体が「使い方マニュアル」になっており、LLMが正しい判断を下せる情報が全て含まれている。

---

## 4. エージェントループの比較

### 4.1 myagentのループ構造

```
User Input
  → SystemMessage + HumanMessage
  → LangGraph StateGraph ループ (max 20)
    → agent_node: LLM呼び出し (bind_tools)
    → should_continue: tool_callsがあるか?
    → tool_node_wrapper: バリデーション → 確認 → 実行
    → agent_node に戻る
  → 最終メッセージを返す
```

**特徴**:
- LangGraphの標準的なReActパターン
- `_truncate_messages()`: 直近20メッセージ + 8000文字制限
- Critic: 同一ツール呼び出し検知 (2連続) + エラー3回繰り返し検知
- コンテキスト圧縮: 80%閾値でDCP + LLM要約

### 4.2 Claude Codeのループ構造（推定）

```
User Input
  → 巨大なSystemMessage (CLAUDE.md + スキル + 環境情報)
  → Claude API呼び出し (native tool_use)
  → tool_useがあれば実行
    → 権限チェック (allow/deny/ask)
    → ツール実行
    → 結果をメッセージに追加
  → Claude API再呼び出し
  → 繰り返し
  → 最終テキスト応答を返す
```

**特徴**:
- **LangChain/LangGraphを使わない** — Claude APIのネイティブtool_useを直接使用
- メッセージの自動圧縮（コンテキスト上限接近時にsystem-reminderで要約を注入）
- サブエージェント: Agentツールで別プロセスを起動（worktree分離可能）
- 並列ツール呼び出し: 単一レスポンス内で複数ツールを同時実行

### 4.3 重要な差分

| 観点 | myagent | Claude Code |
|------|---------|-------------|
| フレームワーク | LangGraph (間接層あり) | ネイティブClaude API (直接) |
| ツールバインド | `model.bind_tools()` | API native tool_use |
| メッセージ切り詰め | 固定20件 + 8000文字 | 動的圧縮 + system-reminder |
| 並列ツール | 非対応（1ツール/ステップ） | 1レスポンスで複数ツール並列 |
| サブエージェント | Orchestrator (同一プロセス) | Agent tool (別プロセス/worktree) |
| ループ上限 | 20回 | 制限なし（実質無限） |
| エラー復旧 | Critic (パターン検知で停止) | プロンプト指示（別アプローチを試せ） |

---

## 5. コンテキスト管理の比較

### 5.1 myagent

```python
# トークン推定: 1 token ≈ 4 chars (粗い近似)
# 圧縮閾値: コンテキストウィンドウの80%
# DCP: read→write の冗長出力を刈り込み
# 圧縮: LLMで古いメッセージを要約
# 固定: SystemMessage + 直近6メッセージ保持
```

**問題点**:
- トークン推定が粗い（日本語は1文字≈1-2トークンだが4文字=1トークンと計算）
- 圧縮時に重要な文脈が失われやすい
- `_truncate_messages()`とContextManager圧縮の二重管理

### 5.2 Claude Code

```
# Anthropicのネイティブトークンカウント（正確）
# 自動圧縮: コンテキスト上限接近時にsystem-reminderで注入
# 圧縮内容: 前半の会話を要約し、後半を完全保持
# 圧縮後も重要な情報はsystem-reminderとして永続化
# CLAUDE.md: 毎回読み込まれる固定コンテキスト
```

**優位性**:
- トークンカウントが正確（API側で管理）
- 圧縮が透明（要約内容がsystem-reminderとして見える）
- CLAUDE.mdが常にコンテキストに存在（プロジェクト知識の永続化）
- 長期記憶（memory system）でセッション跨ぎの情報保持

---

## 6. ツールの使い分け指示の比較

### 6.1 myagentの課題

myagentのbase.txtには「ツールを使って作業を完了してください」としか書かれておらず、**どのツールをどの場面で使うべきか**の指示がない。

結果:
- LLMが `run_command` で `cat file.txt` を実行する（`read_file`を使うべき）
- `run_command` で `grep` を実行する（`grep_search`を使うべき）
- 既存ファイルを読まずに`write_file`で上書きする

### 6.2 Claude Codeの解決策

Claude Codeはシステムプロンプトに**ツール使い分けマトリクス**を明記:

```
# Using your tools
- Do NOT use Bash to run commands when a relevant dedicated tool is provided:
  - To read files use Read instead of cat, head, tail, or sed
  - To edit files use Edit instead of sed or awk
  - To create files use Write instead of cat with heredoc or echo redirection
  - To search for files use Glob instead of find or ls
  - To search the content of files, use Grep instead of grep or rg
  - Reserve Bash exclusively for system commands that require shell execution
```

さらに各ツールのdescription内でも:
```
# Edit tool
- You must use your Read tool at least once before editing.
  This tool will error if you attempt an edit without reading the file.
```

---

## 7. タスク実行品質の比較

### 7.1 myagentの課題

- **Over-engineering**: 依頼以上のことをしがち（docstring追加、型注釈追加、リファクタリング）
- **確認不足**: ファイルを読まずに変更を提案
- **冗長な出力**: 何をしたかの長い説明
- **安全性**: 破壊的操作への配慮不足

### 7.2 Claude Codeの対策（プロンプト指示）

```
# Over-engineering禁止
- Don't add features, refactor code, or make "improvements" beyond what was asked
- Don't add docstrings, comments, or type annotations to code you didn't change
- Don't add error handling for scenarios that can't happen
- Don't create helpers for one-time operations
- Three similar lines of code is better than a premature abstraction

# 出力効率
- Go straight to the point. Try the simplest approach first
- Lead with the answer or action, not the reasoning
- If you can say it in one sentence, don't use three

# 安全性
- Consider the reversibility and blast radius of actions
- For hard-to-reverse actions, check with the user before proceeding
- NEVER run destructive git commands unless explicitly requested
```

---

## 8. サブエージェント・並列処理の比較

### 8.1 myagent

```python
# Planner: LLMでサブタスク分解 → JSON
# Orchestrator: トポロジカルソート → 並列実行
# Worker: 独立したAgentRunnerインスタンス
# 制限: max_workers=3, ファイル競合検知あり
```

**問題点**:
- Plannerの分解精度がLLMの1回のJSON出力に依存
- Workerは独立だがコンテキスト共有なし
- 全体の結果を集約する仕組みが弱い

### 8.2 Claude Code

```
# Agent tool: 9種の専門エージェント
# - general-purpose: 複雑なマルチステップタスク
# - Explore: コードベース探索（quick/medium/very thorough）
# - Plan: アーキテクチャ設計
# - implementation-validator: 実装検証
# - doc-reviewer: ドキュメントレビュー
# 各エージェントに専用のツールセットと権限
# foreground/background 使い分け
# worktree分離: gitワークツリーで独立実行
```

**優位性**:
- エージェントタイプが明確に分かれている（LLMが適切なタイプを選択可能）
- 各エージェントに異なるツールセットを割り当て（例: Exploreは書き込み不可）
- worktreeでリポジトリの独立コピーを使える
- background実行で並行作業が可能

---

## 9. 具体的な精度改善ポイント（推奨アクション）

### 優先度: 高（即効性あり）

#### 9.1 システムプロンプトの大幅拡充

**現状**: base.txtは30行、抽象的な指示のみ
**目標**: Claude Code並みの詳細な行動ガイドライン

追加すべき内容:
1. **ツール使い分けルール**: 「Bashの代わりに専用ツールを使え」のマトリクス
2. **Over-engineering禁止**: 具体例付きのアンチパターン集
3. **出力スタイル**: 簡潔さ、フォーマット、トーンの指示
4. **安全性ガイドライン**: 破壊的操作の確認フロー
5. **コード変更前の必須手順**: 「まず読め、次に検索しろ、それから変更しろ」

#### 9.2 ツールdescriptionの拡充

**現状**: 1-2文の簡潔な説明
**目標**: 使い方マニュアル相当の詳細な説明

各ツールに追加すべき情報:
- パラメータの使い分け例
- エッジケースの処理方法
- 他ツールとの使い分けルール
- やってはいけない使い方
- 出力の読み方

#### 9.3 並列ツール呼び出しの対応

**現状**: 1ターンに1ツール呼び出し
**目標**: 独立したツール呼び出しを同時に実行

LangGraphのToolNodeを拡張し、LLMが1レスポンスで複数のtool_callsを返した場合に並列実行する（既にOpenAI/Claude APIは対応済み。LangGraphのToolNodeも対応しているが、myagentの`tool_node_wrapper`内の逐次確認フローがボトルネック）。

### 優先度: 中（アーキテクチャ改善）

#### 9.4 LangGraph/LangChain依存の見直し

**問題**: LangChainの抽象層がツール定義の自由度を制限し、APIのネイティブ機能を活かしきれない

**検討事項**:
- Claude APIのネイティブtool_useを直接使用する選択肢
- LangChainのBaseTool制約（descriptionの長さ制限、args_schemaの柔軟性）
- bind_tools()によるツール定義のフォーマット変換ロス

#### 9.5 コンテキスト圧縮の高度化

**改善案**:
- トークンカウントの精度向上（tiktoken等を使用）
- 圧縮後の要約品質検証
- 重要メッセージのタグ付けと優先保持
- CLAUDE.md相当の「常に注入される固定コンテキスト」の導入

#### 9.6 エラー回復の高度化

**現状**: Criticがパターン検知で停止
**目標**: 停止ではなく「別アプローチを試す」誘導

Claude Codeのプロンプトには:
```
If your approach is blocked, do not attempt to brute force your way.
Consider alternative approaches or other ways to unblock yourself.
```

myagentのCriticは検知後にAIMessageで「処理を中断します」と返すだけ。代わりに「別のアプローチを3つ提案してください」のような誘導メッセージに変更する。

### 優先度: 低（将来的な拡張）

#### 9.7 長期記憶システム

Claude Codeのauto memory相当のファイルベース記憶を導入。user/feedback/project/referenceの4カテゴリで管理。

#### 9.8 専門サブエージェントの導入

現在のOrchestrator（汎用ワーカー）に加え、用途特化のサブエージェントタイプを追加:
- Explore: 読み取り専用の高速探索
- Validator: 実装品質の検証
- Reviewer: ドキュメントレビュー

---

## 10. 結論

Claude Codeの精度優位性は、特定の高度なアルゴリズムではなく、**プロンプトエンジニアリングの徹底度**に起因する。具体的には:

1. **システムプロンプトの情報量が10倍以上** — LLMに判断に必要な情報を全て提供
2. **ツールdescriptionが使い方マニュアル相当** — 曖昧さを排除
3. **行動制約が具体例付き** — 「やってはいけないこと」が明確
4. **ネイティブAPI活用** — 中間フレームワークのオーバーヘッドなし

myagentの最も効果的な改善は、コードアーキテクチャの変更ではなく、**プロンプトとツール定義の拡充**である。これにより、既存のLangGraph基盤のまま大幅な精度向上が見込める。
