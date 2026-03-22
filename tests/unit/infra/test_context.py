"""ContextManager のテスト."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from myagent.infra.context import (
    ContextManager,
    _count_tokens,
    _load_gitignore_patterns,
    get_message_priority,
    set_message_priority,
)


class Testcount_tokens:
    """_count_tokens ユーティリティ関数のテスト."""

    def test_空文字列は1を返す(self) -> None:
        assert _count_tokens("") == 1

    def test_4文字で1トークンを返す(self) -> None:
        assert _count_tokens("abcd") == 1

    def test_8文字で2トークンを返す(self) -> None:
        assert _count_tokens("abcdefgh") == 2

    def test_100文字で25トークンを返す(self) -> None:
        assert _count_tokens("a" * 100) == 25

    def test_3文字は1トークンを返す(self) -> None:
        # 3 // 4 == 0 → max(1, 0) == 1
        assert _count_tokens("abc") == 1


class TestContextManagerの初期化:
    """ContextManager の初期化テスト."""

    def test_デフォルト値で初期化できる(self) -> None:
        cm = ContextManager()
        assert cm._max_context_tokens == 128_000
        assert cm._compress_threshold == 0.8
        assert cm._max_output_lines == 200

    def test_カスタム値で初期化できる(self) -> None:
        cm = ContextManager(
            max_context_tokens=50_000,
            compress_threshold=0.7,
            max_output_lines=100,
        )
        assert cm._max_context_tokens == 50_000
        assert cm._compress_threshold == 0.7
        assert cm._max_output_lines == 100

    def test_project_indexは初期状態でNone(self) -> None:
        cm = ContextManager()
        assert cm.project_index is None


class TestContextManagerのトークン計算:
    """ContextManager のトークン計算テスト."""

    def test_count_tokens_で文字列のトークン数を取得できる(self) -> None:
        cm = ContextManager()
        assert cm.count_tokens("a" * 40) == 10

    def test_messages_token_countで文字列コンテンツのトークン数を計算できる(
        self,
    ) -> None:
        cm = ContextManager()
        messages = [
            HumanMessage(content="a" * 40),  # 10 tokens
            AIMessage(content="b" * 80),  # 20 tokens
        ]
        assert cm.messages_token_count(messages) == 30

    def test_messages_token_countでリスト形式コンテンツも計算できる(self) -> None:
        cm = ContextManager()
        msg = AIMessage(content=[{"type": "text", "text": "a" * 40}])
        result = cm.messages_token_count([msg])
        assert result == 10

    def test_messages_token_countで空リストは0を返す(self) -> None:
        cm = ContextManager()
        assert cm.messages_token_count([]) == 0


class TestContextManagerのneeds_compression:
    """needs_compression メソッドのテスト."""

    def test_閾値未満では圧縮不要(self) -> None:
        cm = ContextManager(max_context_tokens=1000, compress_threshold=0.8)
        # threshold = 800 tokens
        # messages = 10 tokens (40 chars)
        messages = [HumanMessage(content="a" * 40)]
        assert cm.needs_compression(messages) is False

    def test_閾値以上で圧縮が必要(self) -> None:
        cm = ContextManager(max_context_tokens=100, compress_threshold=0.8)
        # threshold = 80 tokens
        # messages = 100 tokens (400 chars)
        messages = [HumanMessage(content="a" * 400)]
        assert cm.needs_compression(messages) is True

    def test_閾値ちょうどで圧縮が必要(self) -> None:
        cm = ContextManager(max_context_tokens=100, compress_threshold=0.8)
        # threshold = 80 tokens
        # messages = 80 tokens (320 chars)
        messages = [HumanMessage(content="a" * 320)]
        assert cm.needs_compression(messages) is True


class TestContextManagerのcontext_usage_ratio:
    """context_usage_ratio メソッドのテスト."""

    def test_使用率を計算できる(self) -> None:
        cm = ContextManager(max_context_tokens=1000)
        # 250 tokens (1000 chars)
        messages = [HumanMessage(content="a" * 1000)]
        ratio = cm.context_usage_ratio(messages)
        assert ratio == pytest.approx(0.25)

    def test_max_context_tokensが0の場合は0を返す(self) -> None:
        cm = ContextManager(max_context_tokens=1)
        cm._max_context_tokens = 0
        assert cm.context_usage_ratio([]) == 0.0


class TestContextManagerのtruncate_output:
    """truncate_output メソッドのテスト."""

    def test_行数が上限以内なら変更なし(self) -> None:
        cm = ContextManager(max_output_lines=10)
        output = "\n".join(f"line{i}" for i in range(5))
        assert cm.truncate_output(output) == output

    def test_行数が上限を超えると省略される(self) -> None:
        cm = ContextManager(max_output_lines=10)
        output = "\n".join(f"line{i}" for i in range(20))
        result = cm.truncate_output(output)
        assert "省略" in result
        assert "line0" in result
        assert "line19" in result
        lines = result.splitlines()
        # 先頭5行 + 空行 + 省略行 + 空行 + 末尾5行 = 13行
        assert len(lines) <= 13

    def test_カスタムmax_linesを指定できる(self) -> None:
        cm = ContextManager(max_output_lines=100)
        output = "\n".join(f"line{i}" for i in range(20))
        # max_lines=5 を指定
        result = cm.truncate_output(output, max_lines=5)
        assert "省略" in result

    def test_行数ちょうどでは変更なし(self) -> None:
        cm = ContextManager(max_output_lines=5)
        output = "\n".join(f"line{i}" for i in range(5))
        assert cm.truncate_output(output) == output


class TestContextManagerのbuild_project_index:
    """build_project_index メソッドのテスト."""

    def test_存在しないディレクトリはインデックスを構築しない(
        self, tmp_path: Path
    ) -> None:
        cm = ContextManager()
        cm.build_project_index(tmp_path / "nonexistent")
        assert cm.project_index is None

    def test_空のディレクトリでもインデックスを構築できる(self, tmp_path: Path) -> None:
        cm = ContextManager()
        cm.build_project_index(tmp_path)
        assert cm.project_index is not None
        assert tmp_path.name in cm.project_index

    def test_ファイルがインデックスに含まれる(self, tmp_path: Path) -> None:
        cm = ContextManager()
        (tmp_path / "main.py").write_text("print('hello')")
        cm.build_project_index(tmp_path)
        assert cm.project_index is not None
        assert "main.py" in cm.project_index

    def test_gitignoreのパターンが除外される(self, tmp_path: Path) -> None:
        cm = ContextManager()
        (tmp_path / ".gitignore").write_text("*.log\nsecret.txt\n")
        (tmp_path / "main.py").write_text("code")
        (tmp_path / "app.log").write_text("log")
        (tmp_path / "secret.txt").write_text("secret")
        cm.build_project_index(tmp_path)
        assert cm.project_index is not None
        assert "main.py" in cm.project_index
        assert "app.log" not in cm.project_index
        assert "secret.txt" not in cm.project_index

    def test_標準除外パターンが除外される(self, tmp_path: Path) -> None:
        cm = ContextManager()
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "module.pyc").write_text("bytecode")
        (tmp_path / "main.py").write_text("code")
        cm.build_project_index(tmp_path)
        assert cm.project_index is not None
        assert "main.py" in cm.project_index
        assert "__pycache__" not in cm.project_index

    def test_git_ディレクトリが除外される(self, tmp_path: Path) -> None:
        cm = ContextManager()
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("git config")
        (tmp_path / "main.py").write_text("code")
        cm.build_project_index(tmp_path)
        assert cm.project_index is not None
        assert ".git" not in cm.project_index

    def test_ネストしたディレクトリ構造が反映される(self, tmp_path: Path) -> None:
        cm = ContextManager()
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("code")
        cm.build_project_index(tmp_path)
        assert cm.project_index is not None
        assert "src" in cm.project_index
        assert "app.py" in cm.project_index


class TestContextManagerのcompress_messages:
    """compress_messages メソッドのテスト."""

    @pytest.mark.asyncio
    async def test_SystemMessageが保持される(self) -> None:
        cm = ContextManager()
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(
            return_value=AIMessage(content="要約されたメッセージ")
        )

        messages = [
            SystemMessage(content="システムプロンプト"),
            HumanMessage(content="質問1"),
            AIMessage(content="回答1"),
            HumanMessage(content="質問2"),
            AIMessage(content="回答2"),
            HumanMessage(content="質問3"),
            AIMessage(content="回答3"),
            HumanMessage(content="質問4"),  # 直近 6 件
        ]
        result = await cm.compress_messages(messages, mock_model)

        # SystemMessage が先頭に保持されているか
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "システムプロンプト"

    @pytest.mark.asyncio
    async def test_メッセージ数が削減される(self) -> None:
        cm = ContextManager()
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="要約"))

        # 12件の非Systemメッセージ (> _KEEP_RECENT_MESSAGES=6)
        # 圧縮: 12 - 6 = 6件が要約 → 1件の要約 + 6件の直近 = 7件 + 1 System = 8件
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="q1"),
            AIMessage(content="a1"),
            HumanMessage(content="q2"),
            AIMessage(content="a2"),
            HumanMessage(content="q3"),
            AIMessage(content="a3"),
            HumanMessage(content="q4"),
            AIMessage(content="a4"),
            HumanMessage(content="q5"),
            AIMessage(content="a5"),
            HumanMessage(content="q6"),
            AIMessage(content="a6"),
        ]
        original_count = len(messages)
        result = await cm.compress_messages(messages, mock_model)
        # 圧縮後は元のメッセージ数より少ない
        assert len(result) < original_count

    @pytest.mark.asyncio
    async def test_メッセージ数が少ない場合は圧縮しない(self) -> None:
        cm = ContextManager()
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="要約"))

        # 6件以下の非Systemメッセージ
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="q1"),
            AIMessage(content="a1"),
        ]
        result = await cm.compress_messages(messages, mock_model)
        # 変更なし
        assert result == messages

    @pytest.mark.asyncio
    async def test_空リストは変更なし(self) -> None:
        cm = ContextManager()
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(content=""))

        result = await cm.compress_messages([], mock_model)
        assert result == []

    @pytest.mark.asyncio
    async def test_LLM呼び出し失敗時は元のメッセージを返す(self) -> None:
        cm = ContextManager()
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(side_effect=Exception("LLMエラー"))

        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="q1"),
            AIMessage(content="a1"),
            HumanMessage(content="q2"),
            AIMessage(content="a2"),
            HumanMessage(content="q3"),
            AIMessage(content="a3"),
            HumanMessage(content="q4"),
        ]
        result = await cm.compress_messages(messages, mock_model)
        # 元のメッセージがそのまま返される
        assert result == messages


class Testload_gitignore_patterns:
    """_load_gitignore_patterns ユーティリティのテスト."""

    def test_gitignoreが存在しない場合は空リスト(self, tmp_path: Path) -> None:
        patterns = _load_gitignore_patterns(tmp_path)
        assert patterns == []

    def test_コメント行は除外される(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("# comment\n*.log\n")
        patterns = _load_gitignore_patterns(tmp_path)
        assert "# comment" not in patterns
        assert "*.log" in patterns

    def test_空行は除外される(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("\n*.log\n\n")
        patterns = _load_gitignore_patterns(tmp_path)
        assert "" not in patterns
        assert "*.log" in patterns

    def test_末尾スラッシュが除去される(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("dist/\n")
        patterns = _load_gitignore_patterns(tmp_path)
        assert "dist" in patterns
        assert "dist/" not in patterns


class Testメッセージ優先度:
    """set_message_priority / get_message_priority のテスト."""

    def test_デフォルト優先度はnormal(self) -> None:
        msg = HumanMessage(content="テスト")
        assert get_message_priority(msg) == "normal"

    def test_critical優先度を設定できる(self) -> None:
        msg = HumanMessage(content="重要")
        updated = set_message_priority(msg, "critical")
        assert get_message_priority(updated) == "critical"

    def test_low優先度を設定できる(self) -> None:
        msg = HumanMessage(content="低優先")
        updated = set_message_priority(msg, "low")
        assert get_message_priority(updated) == "low"

    def test_元のメッセージは変更されない(self) -> None:
        msg = HumanMessage(content="テスト")
        set_message_priority(msg, "critical")
        assert get_message_priority(msg) == "normal"


class TestInceptionMessage:
    """Inception Message のテスト."""

    def test_inception_messageを登録できる(self) -> None:
        cm = ContextManager()
        cm.add_inception_message("重要な制約条件")
        assert cm.get_inception_messages() == ["重要な制約条件"]

    def test_複数のinception_messageを登録できる(self) -> None:
        cm = ContextManager()
        cm.add_inception_message("制約1")
        cm.add_inception_message("制約2")
        assert cm.get_inception_messages() == ["制約1", "制約2"]

    def test_初期状態ではinception_messageは空(self) -> None:
        cm = ContextManager()
        assert cm.get_inception_messages() == []

    @pytest.mark.asyncio
    async def test_inception_messageは圧縮で保持される(self) -> None:
        cm = ContextManager(max_context_tokens=100, compress_threshold=0.1)
        cm.add_inception_message("絶対に保持する制約")

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=MagicMock(content="要約された内容")
        )

        messages = [
            SystemMessage(content="システム"),
            HumanMessage(content="古いメッセージ1" * 100),
            AIMessage(content="回答1" * 100),
            HumanMessage(content="古いメッセージ2" * 100),
            AIMessage(content="回答2" * 100),
            HumanMessage(content="最近1"),
            AIMessage(content="最近2"),
            HumanMessage(content="最近3"),
            AIMessage(content="最近4"),
            HumanMessage(content="最近5"),
            AIMessage(content="最近6"),
        ]

        compressed = await cm.compress_messages(messages, mock_model)

        # inception message が含まれていることを確認
        contents = [
            m.content for m in compressed if isinstance(m.content, str)
        ]
        has_inception = any("絶対に保持する制約" in c for c in contents)
        assert has_inception


class TestCritical優先度の圧縮:
    """critical 優先度メッセージの圧縮テスト."""

    @pytest.mark.asyncio
    async def test_criticalメッセージは圧縮で保持される(self) -> None:
        cm = ContextManager(max_context_tokens=100, compress_threshold=0.1)

        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=MagicMock(content="要約")
        )

        critical_msg = set_message_priority(
            HumanMessage(content="critical_content_here"), "critical"
        )

        messages = [
            SystemMessage(content="システム"),
            critical_msg,
            HumanMessage(content="通常メッセージ" * 100),
            AIMessage(content="回答" * 100),
            HumanMessage(content="最近1"),
            AIMessage(content="最近2"),
            HumanMessage(content="最近3"),
            AIMessage(content="最近4"),
            HumanMessage(content="最近5"),
            AIMessage(content="最近6"),
        ]

        compressed = await cm.compress_messages(messages, mock_model)

        # critical メッセージが保持されていることを確認
        contents = [
            m.content for m in compressed if isinstance(m.content, str)
        ]
        has_critical = any("critical_content_here" in c for c in contents)
        assert has_critical


class TestDCP:
    """Dynamic Context Pruning のテスト."""

    def test_write後のread_file結果が刈り込まれる(self) -> None:
        cm = ContextManager()
        messages: list[BaseMessage] = [
            HumanMessage(content="ファイルを読んで"),
            ToolMessage(
                content="ファイルの内容: hello world",
                tool_call_id="1",
                name="read_file",
            ),
            HumanMessage(content="編集して"),
            ToolMessage(
                content="ファイルを編集しました",
                tool_call_id="2",
                name="edit_file",
            ),
        ]

        result = cm.prune_redundant_tool_outputs(messages)

        # read_file の出力が短縮されている
        assert "出力省略" in result[1].content
        # edit_file の出力はそのまま
        assert "ファイルを編集しました" in result[3].content

    def test_write前のread_file結果は保持される(self) -> None:
        cm = ContextManager()
        messages: list[BaseMessage] = [
            ToolMessage(
                content="ファイルの内容: hello",
                tool_call_id="1",
                name="read_file",
            ),
        ]

        result = cm.prune_redundant_tool_outputs(messages)

        # write がないので read_file 結果はそのまま
        assert "ファイルの内容: hello" in result[0].content

    def test_list_directory重複が刈り込まれる(self) -> None:
        cm = ContextManager()
        messages: list[BaseMessage] = [
            ToolMessage(
                content="dir1/\nfile1.py",
                tool_call_id="1",
                name="list_directory",
            ),
            HumanMessage(content="もう一度"),
            ToolMessage(
                content="dir1/\nfile1.py\nfile2.py",
                tool_call_id="2",
                name="list_directory",
            ),
        ]

        result = cm.prune_redundant_tool_outputs(messages)

        # 古い list_directory が短縮され、最新は保持
        assert "出力省略" in result[0].content
        assert "file2.py" in result[2].content

    def test_glob_search重複が刈り込まれる(self) -> None:
        cm = ContextManager()
        messages: list[BaseMessage] = [
            ToolMessage(
                content="src/main.py",
                tool_call_id="1",
                name="glob_search",
            ),
            ToolMessage(
                content="src/main.py\nsrc/utils.py",
                tool_call_id="2",
                name="glob_search",
            ),
        ]

        result = cm.prune_redundant_tool_outputs(messages)

        assert "出力省略" in result[0].content
        assert "src/utils.py" in result[1].content

    def test_空メッセージリストはそのまま返す(self) -> None:
        cm = ContextManager()
        assert cm.prune_redundant_tool_outputs([]) == []

    def test_ToolMessage以外のメッセージは影響を受けない(self) -> None:
        cm = ContextManager()
        messages: list[BaseMessage] = [
            HumanMessage(content="テスト"),
            AIMessage(content="回答"),
        ]

        result = cm.prune_redundant_tool_outputs(messages)

        assert result[0].content == "テスト"
        assert result[1].content == "回答"
