"""コンテキスト管理モジュール.

会話履歴のトークン追跡・圧縮・プロジェクトインデックス管理を提供する。
優先度ベースの圧縮、固定コンテキスト（Inception Message）、
Dynamic Context Pruning（DCP）をサポートする。
"""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

MessagePriority = Literal["critical", "normal", "low"]

# プロジェクトインデックスのデフォルト制限
_MAX_INDEX_FILES = 200
_MAX_INDEX_DEPTH = 5

# 標準除外パターン（.gitignore に書かれていなくても常に除外）
_DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    ".git",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "*.egg-info",
    ".DS_Store",
    # myagent設定ディレクトリ（スキル・プラグイン等の内部ファイルはプロジェクト索引から除外）
    ".myagent",
    # 機密ファイル（ファイル名のみであっても露出しないように除外）
    ".env",
    ".env.*",
    "*credentials*",
    "*secret*",
    "*.pem",
    "*.key",
    "*.p12",
    "id_rsa",
    "id_ed25519",
]

# 圧縮時に保持する直近メッセージ数
_KEEP_RECENT_MESSAGES = 6

# DCP対象のツール名
_DCP_READ_TOOLS = {"read_file"}
_DCP_WRITE_TOOLS = {"edit_file", "write_file"}
_DCP_LIST_TOOLS = {"list_directory", "glob_search"}

# DCP短縮時のサマリーテンプレート
_DCP_PRUNED_TEMPLATE = "(出力省略: {tool_name} の結果は後続の操作で上書きされました)"
_DCP_DUPLICATE_TEMPLATE = "(出力省略: {tool_name} の最新の結果が後方に存在します)"


def set_message_priority(
    msg: BaseMessage, priority: MessagePriority
) -> BaseMessage:
    """メッセージに優先度を設定する.

    BaseMessage の additional_kwargs に priority キーを追加する。

    Args:
        msg: 対象メッセージ。
        priority: 設定する優先度。

    Returns:
        優先度が設定されたメッセージ（新しいコピー）。
    """
    new_kwargs = {**msg.additional_kwargs, "priority": priority}
    return msg.model_copy(update={"additional_kwargs": new_kwargs})


def get_message_priority(msg: BaseMessage) -> MessagePriority:
    """メッセージの優先度を取得する.

    Args:
        msg: 対象メッセージ。

    Returns:
        メッセージの優先度。未設定の場合は "normal"。
    """
    raw = msg.additional_kwargs.get("priority", "normal")
    return raw  # type: ignore[no-any-return]


def _count_tokens(text: str) -> int:
    """テキストのトークン数を推定する.

    文字数ベースの近似（1 token ≈ 4 chars）。
    ゼロ文字の場合は 1 を返す。

    Args:
        text: 対象テキスト。

    Returns:
        推定トークン数。
    """
    return max(1, len(text) // 4)


def _load_gitignore_patterns(root: Path) -> list[str]:
    """指定ディレクトリの .gitignore パターンを読み込む.

    Args:
        root: プロジェクトルートディレクトリ。

    Returns:
        .gitignore パターンのリスト。ファイルがなければ空リスト。
    """
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        return []
    patterns: list[str] = []
    try:
        for line in gitignore_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                # 末尾の / は除去（ディレクトリを示すが fnmatch では不要）
                patterns.append(line.rstrip("/"))
    except OSError:
        logger.warning(".gitignore の読み込みに失敗しました: %s", gitignore_path)
    return patterns


def _is_excluded(path: Path, root: Path, patterns: list[str]) -> bool:
    """パスが除外対象かどうかを判定する.

    標準除外パターンおよびカスタムパターン（.gitignore 等）を両方チェックする。

    Args:
        path: チェック対象のパス。
        root: プロジェクトルートディレクトリ。
        patterns: 除外パターンのリスト。

    Returns:
        除外対象なら True。
    """
    name = path.name
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False

    # 標準除外パターンをチェック（ファイル名またはパスの各部分）
    for default_pat in _DEFAULT_EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(name, default_pat):
            return True
        for part in rel.parts:
            if fnmatch.fnmatch(part, default_pat):
                return True

    # カスタムパターンをチェック
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(str(rel), pattern):
            return True
        for part in rel.parts:
            if fnmatch.fnmatch(part, pattern):
                return True

    return False


def _build_tree_lines(
    directory: Path,
    root: Path,
    patterns: list[str],
    prefix: str = "",
    current_depth: int = 0,
    file_count: list[int] | None = None,
) -> list[str]:
    """ディレクトリツリーの行リストを再帰的に構築する.

    Args:
        directory: 現在のディレクトリ。
        root: プロジェクトルートディレクトリ。
        patterns: 除外パターンリスト。
        prefix: インデントプレフィックス。
        current_depth: 現在の再帰深度。
        file_count: ファイル数のカウンタ（可変リストで共有）。

    Returns:
        ツリー行のリスト。
    """
    if file_count is None:
        file_count = [0]

    if current_depth >= _MAX_INDEX_DEPTH or file_count[0] >= _MAX_INDEX_FILES:
        return []

    lines: list[str] = []
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return []

    valid_entries = [e for e in entries if not _is_excluded(e, root, patterns)]

    for i, entry in enumerate(valid_entries):
        if file_count[0] >= _MAX_INDEX_FILES:
            msg = f"... (上限 {_MAX_INDEX_FILES} ファイルに達しました)"
            lines.append(f"{prefix}{msg}")
            break

        is_last = i == len(valid_entries) - 1
        connector = "└── " if is_last else "├── "
        child_prefix = prefix + ("    " if is_last else "│   ")

        lines.append(f"{prefix}{connector}{entry.name}")
        file_count[0] += 1

        if entry.is_dir():
            sub_lines = _build_tree_lines(
                entry, root, patterns, child_prefix, current_depth + 1, file_count
            )
            lines.extend(sub_lines)

    return lines


class ContextManager:
    """会話コンテキスト管理クラス.

    トークン使用量の追跡、コンテキスト圧縮、プロジェクトインデックス管理を提供する。
    """

    def __init__(
        self,
        max_context_tokens: int = 128_000,
        compress_threshold: float = 0.8,
        max_output_lines: int = 200,
    ) -> None:
        """ContextManager を初期化する.

        Args:
            max_context_tokens: コンテキストウィンドウの最大トークン数。
            compress_threshold: 圧縮を開始するトークン使用率の閾値（0.0〜1.0）。
            max_output_lines: ツール出力のトランケーション上限行数。
        """
        self._max_context_tokens = max_context_tokens
        self._compress_threshold = compress_threshold
        self._max_output_lines = max_output_lines
        self._project_index: str | None = None
        self._working_directory: str = ""
        self._inception_messages: list[str] = []

    def count_tokens(self, text: str) -> int:
        """テキストのトークン数を推定する.

        Args:
            text: 対象テキスト。

        Returns:
            推定トークン数。
        """
        return _count_tokens(text)

    def messages_token_count(self, messages: list[BaseMessage]) -> int:
        """メッセージリストの総トークン数を推定する.

        Args:
            messages: トークン数を計算するメッセージリスト。

        Returns:
            推定トークン数の合計。
        """
        total = 0
        for msg in messages:
            content = msg.content
            if isinstance(content, str):
                total += _count_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        total += _count_tokens(part.get("text", ""))
        return total

    def needs_compression(self, messages: list[BaseMessage]) -> bool:
        """トークン数が圧縮閾値を超えているか判定する.

        Args:
            messages: チェック対象のメッセージリスト。

        Returns:
            圧縮が必要なら True。
        """
        threshold = int(self._max_context_tokens * self._compress_threshold)
        return self.messages_token_count(messages) >= threshold

    def context_usage_ratio(self, messages: list[BaseMessage]) -> float:
        """コンテキストウィンドウの使用率を返す.

        Args:
            messages: チェック対象のメッセージリスト。

        Returns:
            使用率（0.0〜1.0）。1.0 を超える場合もある。
        """
        if self._max_context_tokens <= 0:
            return 0.0
        return self.messages_token_count(messages) / self._max_context_tokens

    def add_inception_message(self, content: str) -> None:
        """固定コンテキスト（Inception Message）を登録する.

        Inception Message は圧縮時に要約対象から除外され、常に保持される。

        Args:
            content: 固定コンテキストの内容。
        """
        self._inception_messages.append(content)

    def get_inception_messages(self) -> list[str]:
        """登録済みの固定コンテキストを返す.

        Returns:
            固定コンテキストのリスト。
        """
        return list(self._inception_messages)

    def prune_redundant_tool_outputs(
        self, messages: list[BaseMessage]
    ) -> list[BaseMessage]:
        """冗長なツール出力を動的に刈り込む（DCP）.

        以下のルールで不要な中間出力を短縮する:
        - read_file の結果で、そのファイルが後に edit_file/write_file で
          上書きされた場合、古い read_file 結果を短縮
        - list_directory/glob_search の結果が複数回ある場合、
          最新以外を短縮

        Args:
            messages: 刈り込み対象のメッセージリスト。

        Returns:
            刈り込み後のメッセージリスト。
        """
        if not messages:
            return messages

        # ToolMessage のインデックスとツール情報を収集
        tool_infos: list[tuple[int, str, str]] = []  # (index, tool_name, file_path)
        for i, msg in enumerate(messages):
            if isinstance(msg, ToolMessage):
                tool_name = getattr(msg, "name", "") or ""
                # ToolMessage の tool_call_id から推定できないため
                # name 属性を使用する
                file_path = ""
                if tool_name in (_DCP_READ_TOOLS | _DCP_WRITE_TOOLS):
                    # AIMessage の tool_calls から引数を取得は困難なため
                    # ToolMessage の content からファイルパスを推定しない
                    # 代わりにツール名のみで判断する
                    file_path = tool_name  # グルーピングキーとして使用
                tool_infos.append((i, tool_name, file_path))

        if not tool_infos:
            return messages

        # 上書きされた read_file の検出
        # write/edit ツールが実行された場合、それ以前の read_file 結果を短縮
        write_indices: set[int] = set()
        for i, tool_name, _ in tool_infos:
            if tool_name in _DCP_WRITE_TOOLS:
                write_indices.add(i)

        prune_indices: set[int] = set()

        if write_indices:
            last_write_idx = max(write_indices)
            for i, tool_name, _ in tool_infos:
                if tool_name in _DCP_READ_TOOLS and i < last_write_idx:
                    prune_indices.add(i)

        # list_directory/glob_search の重複検出（最新以外を短縮）
        list_tool_indices: dict[str, list[int]] = {}
        for i, tool_name, _ in tool_infos:
            if tool_name in _DCP_LIST_TOOLS:
                list_tool_indices.setdefault(tool_name, []).append(i)

        for _tool_name, indices in list_tool_indices.items():
            if len(indices) > 1:
                # 最新以外を刈り込み対象にする
                for idx in indices[:-1]:
                    prune_indices.add(idx)

        if not prune_indices:
            return messages

        # メッセージリストを再構築
        result: list[BaseMessage] = []
        for i, msg in enumerate(messages):
            if i in prune_indices:
                tool_name = getattr(msg, "name", "") or "tool"
                if tool_name in _DCP_READ_TOOLS:
                    template = _DCP_PRUNED_TEMPLATE
                else:
                    template = _DCP_DUPLICATE_TEMPLATE
                pruned = msg.model_copy(
                    update={"content": template.format(tool_name=tool_name)}
                )
                result.append(pruned)
            else:
                result.append(msg)

        pruned_count = len(prune_indices)
        logger.info("DCP: %d件のToolMessage出力を短縮しました", pruned_count)
        return result

    async def compress_messages(
        self,
        messages: list[BaseMessage],
        model: BaseChatModel,
    ) -> list[BaseMessage]:
        """古い会話履歴を LLM で要約・圧縮する.

        SystemMessage を先頭に保持し、古いメッセージを要約した
        HumanMessage に置き換える。
        直近 _KEEP_RECENT_MESSAGES 件のメッセージはそのまま保持する。
        priority が "critical" のメッセージと Inception Message は
        要約対象から除外して保持する。

        Args:
            messages: 圧縮対象のメッセージリスト。
            model: 要約に使用する LLM モデル。

        Returns:
            圧縮後のメッセージリスト。LLM 呼び出し失敗時は元のリストを返す。
        """
        if not messages:
            return messages

        # SystemMessage を分離
        system_msgs: list[BaseMessage] = []
        other_msgs: list[BaseMessage] = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_msgs.append(msg)
            else:
                other_msgs.append(msg)

        # 直近メッセージを保持し、古いメッセージを要約対象にする
        if len(other_msgs) <= _KEEP_RECENT_MESSAGES:
            # 圧縮するほどメッセージがない
            return messages

        to_summarize = other_msgs[:-_KEEP_RECENT_MESSAGES]
        recent = other_msgs[-_KEEP_RECENT_MESSAGES:]

        # critical メッセージを要約対象から除外して保持
        critical_msgs: list[BaseMessage] = []
        summarize_targets: list[BaseMessage] = []
        for msg in to_summarize:
            if get_message_priority(msg) == "critical":
                critical_msgs.append(msg)
            else:
                summarize_targets.append(msg)

        # Inception Message を HumanMessage として保持
        inception_msgs: list[BaseMessage] = []
        for content in self._inception_messages:
            inception_msgs.append(
                HumanMessage(content=f"[固定コンテキスト]\n{content}")
            )

        # 要約プロンプトを構築
        conversation_text = "\n".join(
            f"[{msg.__class__.__name__}]: {msg.content}"
            for msg in summarize_targets
            if isinstance(msg.content, str)
        )

        if not conversation_text.strip():
            # 要約対象が空の場合（全てcriticalだった場合）
            compressed = (
                list(system_msgs)
                + inception_msgs
                + critical_msgs
                + list(recent)
            )
            return compressed

        summary_prompt = (
            "以下の会話履歴を、重要な情報・決定・ファイル変更を漏らさず"
            "簡潔に要約してください。要約のみを返してください。\n\n"
            f"{conversation_text}"
        )

        try:
            summary_response = await model.ainvoke(
                [HumanMessage(content=summary_prompt)]
            )
            summary_content = summary_response.content
            if not isinstance(summary_content, str):
                summary_content = str(summary_content)

            summary_msg = HumanMessage(content=f"[会話履歴の要約]\n{summary_content}")
            compressed = (
                list(system_msgs)
                + inception_msgs
                + critical_msgs
                + [summary_msg]
                + list(recent)
            )
            logger.info(
                "コンテキスト圧縮完了: %d件 → %d件",
                len(messages),
                len(compressed),
            )
            return compressed

        except Exception as e:
            logger.warning("コンテキスト圧縮に失敗しました（元の履歴を使用）: %s", e)
            return messages

    def truncate_output(self, output: str, max_lines: int | None = None) -> str:
        """長いツール出力を先頭・末尾のみに切り詰める.

        Args:
            output: ツール出力文字列。
            max_lines: 最大行数。None の場合は初期化時の値を使用。

        Returns:
            切り詰め後の文字列。上限以内なら変更なし。
        """
        limit = max_lines if max_lines is not None else self._max_output_lines
        lines = output.splitlines()
        if len(lines) <= limit:
            return output

        half = limit // 2
        head = lines[:half]
        tail = lines[-half:]
        omitted = len(lines) - limit
        return "\n".join(head) + f"\n\n... ({omitted}行省略) ...\n\n" + "\n".join(tail)

    def build_project_index(self, root_dir: str | Path) -> None:
        """プロジェクトのファイルツリーをインデックス化して内部に保持する.

        .gitignore パターンと標準除外パターンを適用してファイルツリーを構築する。

        Args:
            root_dir: プロジェクトルートディレクトリ。
        """
        root = Path(root_dir).resolve()
        if not root.exists() or not root.is_dir():
            logger.warning(
                "プロジェクトインデックス構築失敗: ディレクトリが存在しません: %s",
                root,
            )
            return

        patterns = _load_gitignore_patterns(root)
        file_count: list[int] = [0]
        tree_lines = _build_tree_lines(root, root, patterns, file_count=file_count)

        self._project_index = root.name + "/\n" + "\n".join(tree_lines)
        self._working_directory = str(root)
        logger.info(
            "プロジェクトインデックス構築完了: %s (%d エントリ)",
            root,
            file_count[0],
        )

    @property
    def project_index(self) -> str | None:
        """インデックス化済みのプロジェクトファイルツリー文字列.

        Returns:
            ファイルツリー文字列。未構築の場合は None。
        """
        return self._project_index

    @property
    def working_directory(self) -> str:
        """作業ディレクトリの絶対パス.

        Returns:
            作業ディレクトリの絶対パス文字列。未設定の場合は空文字列。
        """
        return self._working_directory
