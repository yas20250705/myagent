# 実装ガイド (Implementation Guide)

## Python 規約

### 型ヒント

**組み込み型の使用**:
```python
# ✅ 良い例: 組み込み型を使用（Python 3.10+）
def process_items(items: list[str]) -> dict[str, int]:
    return {item: items.count(item) for item in items}

# ❌ 悪い例: typing モジュールの旧スタイル
from typing import List, Dict
def process_items(items: List[str]) -> Dict[str, int]: ...
```

**型注釈の原則**:
```python
# ✅ 良い例: 明示的な型注釈
def calculate_total(prices: list[float]) -> float:
    return sum(prices)

# ❌ 悪い例: 型注釈なし
def calculate_total(prices):  # 型が不明
    return sum(prices)
```

**dataclass と TypedDict**:
```python
from dataclasses import dataclass
from typing import TypedDict, Literal

# dataclass: ミュータブルなエンティティ
@dataclass
class Task:
    id: str
    title: str
    completed: bool

# TypedDict: 辞書の型定義
class TaskDict(TypedDict):
    id: str
    title: str

# Literal: 列挙値
TaskStatus = Literal["todo", "in_progress", "completed"]
TaskId = str
```

### 命名規則

**変数・関数**:
```python
# 変数: snake_case、名詞
user_name = "John"
task_list: list[Task] = []
is_completed = True

# 関数: snake_case、動詞で始める
def fetch_user_data() -> User: ...
def validate_email(email: str) -> None: ...
def calculate_total_price(items: list[Item]) -> float: ...

# Boolean: is_, has_, should_, can_ で始める
is_valid = True
has_permission = False
should_retry = True
can_delete = False
```

**クラス**:
```python
# クラス: PascalCase、名詞
class TaskManager: ...
class UserAuthenticationService: ...

# Protocol（インターフェース相当）
from typing import Protocol
class TaskRepository(Protocol):
    def save(self, task: Task) -> None: ...

# 型エイリアス: PascalCase
TaskStatus = Literal["todo", "in_progress", "completed"]
```

**定数**:
```python
# UPPER_SNAKE_CASE
MAX_RETRY_COUNT = 3
API_BASE_URL = "https://api.example.com"
DEFAULT_TIMEOUT = 5000

# 設定オブジェクトの場合
CONFIG = {
    "max_retry_count": 3,
    "api_base_url": "https://api.example.com",
    "default_timeout": 5000,
}
```

**ファイル名**:
```python
# モジュールファイル: snake_case
# task_service.py
# user_repository.py

# ユーティリティ: snake_case
# format_date.py
# validate_email.py

# 定数: snake_case
# api_endpoints.py
# error_messages.py
```

### 関数設計

**単一責務の原則**:
```python
# ✅ 良い例: 単一の責務
def calculate_total_price(items: list[CartItem]) -> float:
    return sum(item.price * item.quantity for item in items)

def format_price(amount: float) -> str:
    return f"¥{amount:,.0f}"

# ❌ 悪い例: 複数の責務
def calculate_and_format_price(items: list[CartItem]) -> str:
    total = sum(item.price * item.quantity for item in items)
    return f"¥{total:,.0f}"
```

**関数の長さ**:
- 目標: 20行以内
- 推奨: 50行以内
- 100行以上: リファクタリングを検討

**パラメータの数**:
```python
# ✅ 良い例: dataclassでまとめる
@dataclass
class CreateTaskOptions:
    title: str
    description: str | None = None
    priority: Literal["high", "medium", "low"] = "medium"
    due_date: datetime | None = None

def create_task(options: CreateTaskOptions) -> Task: ...

# ❌ 悪い例: パラメータが多すぎる
def create_task(
    title: str,
    description: str,
    priority: str,
    due_date: datetime,
    tags: list[str],
    assignee: str,
) -> Task: ...
```

### エラーハンドリング

**カスタム例外クラス**:
```python
class ValidationError(Exception):
    def __init__(self, message: str, field: str, value: object) -> None:
        super().__init__(message)
        self.field = field
        self.value = value


class NotFoundError(Exception):
    def __init__(self, resource: str, id: str) -> None:
        super().__init__(f"{resource} not found: {id}")
        self.resource = resource
        self.id = id


class DatabaseError(Exception):
    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause
```

**エラーハンドリングパターン**:
```python
# ✅ 良い例: 適切なエラーハンドリング
def get_task(id: str) -> Task:
    try:
        task = repository.find_by_id(id)

        if task is None:
            raise NotFoundError("Task", id)

        return task
    except NotFoundError:
        # 予期されるエラー: 適切に処理
        logger.warning(f"タスクが見つかりません: {id}")
        raise
    except Exception as e:
        # 予期しないエラー: ラップして上位に伝播
        raise DatabaseError("タスクの取得に失敗しました") from e

# ❌ 悪い例: エラーを無視
def get_task(id: str) -> Task | None:
    try:
        return repository.find_by_id(id)
    except Exception:
        return None  # エラー情報が失われる
```

**エラーメッセージ**:
```python
# ✅ 良い例: 具体的で解決策を示す
raise ValidationError(
    f"タイトルは1-200文字で入力してください。現在の文字数: {len(title)}",
    "title",
    title,
)

# ❌ 悪い例: 曖昧で役に立たない
raise ValueError("Invalid input")
```

### 非同期処理（asyncio）

**async/await の使用**:
```python
import asyncio

# ✅ 良い例: async/await
async def fetch_user_tasks(user_id: str) -> list[Task]:
    try:
        user = await user_repository.find_by_id(user_id)
        tasks = await task_repository.find_by_user_id(user.id)
        return tasks
    except Exception as e:
        logger.error(f"タスクの取得に失敗: {e}")
        raise
```

**並列処理**:
```python
# ✅ 良い例: asyncio.gatherで並列実行
async def fetch_multiple_users(ids: list[str]) -> list[User]:
    return await asyncio.gather(
        *[user_repository.find_by_id(id) for id in ids]
    )

# ❌ 悪い例: 逐次実行
async def fetch_multiple_users(ids: list[str]) -> list[User]:
    users = []
    for id in ids:
        user = await user_repository.find_by_id(id)  # 遅い
        users.append(user)
    return users
```

## コメント規約

### ドキュメントコメント

**Docstring形式**:
```python
def create_task(data: CreateTaskData) -> Task:
    """タスクを作成する。

    Args:
        data: 作成するタスクのデータ

    Returns:
        作成されたタスク

    Raises:
        ValidationError: データが不正な場合
        DatabaseError: データベースエラーの場合

    Example:
        >>> task = create_task(CreateTaskData(title="新しいタスク", priority="high"))
        >>> print(task.id)
    """
```

### インラインコメント

**良いコメント**:
```python
# ✅ 理由を説明
# キャッシュを無効化して最新データを取得
cache.clear()

# ✅ 複雑なロジックを説明
# Kadaneのアルゴリズムで最大部分配列和を計算
# 時間計算量: O(n)
max_so_far = arr[0]
max_ending_here = arr[0]

# ✅ TODO・FIXMEを活用
# TODO: キャッシュ機能を実装 (Issue #123)
# FIXME: 大量データでパフォーマンス劣化 (Issue #456)
```

**悪いコメント**:
```python
# ❌ コードの内容を繰り返すだけ
# i を 1 増やす
i += 1

# ❌ コメントアウトされたコード
# old_implementation = lambda: ...  # 削除すべき
```

## セキュリティ

### 入力検証

```python
# ✅ 良い例: 厳密な検証
import re

def validate_email(email: str) -> None:
    if not email:
        raise ValidationError("メールアドレスは必須です", "email", email)

    email_pattern = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    if not email_pattern.match(email):
        raise ValidationError("メールアドレスの形式が不正です", "email", email)

    if len(email) > 254:
        raise ValidationError("メールアドレスが長すぎます", "email", email)

# ❌ 悪い例: 検証なし
def validate_email(email: str) -> None:
    pass
```

### 機密情報の管理

```python
# ✅ 良い例: 環境変数から読み込み
import os

api_key = os.environ.get("API_KEY")
if not api_key:
    raise ValueError("API_KEY環境変数が設定されていません")

# ❌ 悪い例: ハードコード
api_key = "sk-1234567890abcdef"  # 絶対にしない！
```

## パフォーマンス

### データ構造の選択

```python
# ✅ 良い例: 辞書で O(1) アクセス
user_map = {user.id: user for user in users}
user = user_map.get(user_id)  # O(1)

# ❌ 悪い例: リストで O(n) 検索
user = next((u for u in users if u.id == user_id), None)  # O(n)
```

### ループの最適化

```python
# ✅ 良い例: リスト内包表記
results = [process(item) for item in items]

# ✅ ジェネレーター（メモリ効率）
total = sum(item.price for item in items)

# ✅ 通常の for ループ
for item in items:
    process(item)
```

### メモ化

```python
from functools import cache

# 計算結果のキャッシュ（Python 3.9+）
@cache
def expensive_calculation(input_str: str) -> Result:
    # 重い計算
    ...
```

## テストコード

### テストの構造 (Given-When-Then)

```python
class TestTaskService:
    def test_正常なデータでタスクを作成できる(self) -> None:
        # Given: 準備
        service = TaskService(mock_repository)
        task_data = CreateTaskData(
            title="テストタスク",
            description="テスト用の説明",
        )

        # When: 実行
        result = service.create(task_data)

        # Then: 検証
        assert result is not None
        assert result.id is not None
        assert result.title == "テストタスク"

    def test_タイトルが空の場合ValidationErrorをスローする(self) -> None:
        # Given: 準備
        service = TaskService(mock_repository)
        invalid_data = CreateTaskData(title="")

        # When/Then: 実行と検証
        with pytest.raises(ValidationError):
            service.create(invalid_data)
```

### モックの作成

```python
from unittest.mock import MagicMock

# ✅ 良い例: Protocolに基づくモック
mock_repository = MagicMock(spec=TaskRepository)
mock_repository.find_by_id.return_value = mock_task

# テストごとに動作を設定
def test_タスクが存在する場合に返す(self) -> None:
    mock_repository.find_by_id.return_value = mock_task
    result = service.get_task("existing-id")
    assert result == mock_task
```

## リファクタリング

### マジックナンバーの排除

```python
# ✅ 良い例: 定数を定義
MAX_RETRY_COUNT = 3
RETRY_DELAY_SECONDS = 1.0

for attempt in range(MAX_RETRY_COUNT):
    try:
        return fetch_data()
    except Exception:
        if attempt < MAX_RETRY_COUNT - 1:
            time.sleep(RETRY_DELAY_SECONDS)

# ❌ 悪い例: マジックナンバー
for i in range(3):
    try:
        return fetch_data()
    except Exception:
        if i < 2:
            time.sleep(1)
```

### 関数の抽出

```python
# ✅ 良い例: 関数を抽出
def process_order(order: Order) -> None:
    validate_order(order)
    calculate_total(order)
    apply_discounts(order)
    save_order(order)

def validate_order(order: Order) -> None:
    if not order.items:
        raise ValidationError("商品が選択されていません", "items", order.items)

def calculate_total(order: Order) -> None:
    order.total = sum(item.price * item.quantity for item in order.items)

# ❌ 悪い例: 長い関数
def process_order(order: Order) -> None:
    if not order.items:
        raise ValidationError("商品が選択されていません", "items", order.items)
    order.total = sum(item.price * item.quantity for item in order.items)
    if order.coupon:
        order.total -= order.total * order.coupon.discount_rate
    repository.save(order)
```

## チェックリスト

実装完了前に確認:

### コード品質
- [ ] 命名が明確で一貫している（snake_case, PascalCase）
- [ ] 関数が単一の責務を持っている
- [ ] マジックナンバーがない
- [ ] 型ヒントが適切に記載されている
- [ ] エラーハンドリングが実装されている

### セキュリティ
- [ ] 入力検証が実装されている
- [ ] 機密情報がハードコードされていない
- [ ] SQLインジェクション対策がされている

### パフォーマンス
- [ ] 適切なデータ構造を使用している
- [ ] 不要な計算を避けている
- [ ] ループが最適化されている

### テスト
- [ ] pytestでテストが書かれている
- [ ] テストがパスする
- [ ] エッジケースがカバーされている

### ドキュメント
- [ ] 関数・クラスにdocstringがある
- [ ] 複雑なロジックにコメントがある
- [ ] TODOやFIXMEが記載されている（該当する場合）

### ツール
- [ ] `uv run ruff check .` でLintエラーがない
- [ ] `uv run mypy src` で型チェックがパスする
- [ ] `uv run ruff format .` でフォーマットが統一されている
