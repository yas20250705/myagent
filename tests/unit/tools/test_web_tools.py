"""Web検索・Webページ取得ツールのテスト."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from myagent.infra.errors import SecurityError, ToolExecutionError
from myagent.tools.web_tools import (
    DuckDuckGoSearchBackend,
    ExaSearchBackend,
    SearchResult,
    WebFetchTool,
    WebSearchTool,
    _extract_charset,
    _format_search_results,
    _html_to_markdown,
    _html_to_text,
    _parse_ddg_html,
    _validate_url,
)


class TestValidateUrl:
    """URLバリデーション関数のテスト."""

    def test_httpスキームは有効(self) -> None:
        _validate_url("http://example.com")  # エラーが発生しない

    def test_httpsスキームは有効(self) -> None:
        _validate_url("https://example.com/path?q=1")

    def test_ftpスキームは無効(self) -> None:
        with pytest.raises(SecurityError):
            _validate_url("ftp://example.com")

    def test_空文字列は無効(self) -> None:
        with pytest.raises(SecurityError):
            _validate_url("")

    def test_スキームなしは無効(self) -> None:
        with pytest.raises(SecurityError):
            _validate_url("example.com")


class TestExtractCharset:
    """文字コード抽出関数のテスト."""

    def test_utf8を抽出できる(self) -> None:
        assert _extract_charset("text/html; charset=utf-8") == "utf-8"

    def test_charsetなしはutf8を返す(self) -> None:
        assert _extract_charset("text/html") == "utf-8"

    def test_大文字小文字を無視する(self) -> None:
        assert _extract_charset("text/html; CHARSET=UTF-8") == "UTF-8"

    def test_空文字列はutf8を返す(self) -> None:
        assert _extract_charset("") == "utf-8"


class TestHtmlConversion:
    """HTML変換関数のテスト."""

    def test_html_to_textでタグが除去される(self) -> None:
        html = "<h1>Title</h1><p>Body text</p>"
        result = _html_to_text(html)
        assert "Title" in result
        assert "Body text" in result
        assert "<h1>" not in result

    def test_html_to_markdownでタグが変換される(self) -> None:
        html = "<h1>Title</h1><p>Body text</p>"
        result = _html_to_markdown(html)
        assert "Title" in result
        assert "Body text" in result


# ---------------------------------------------------------------------------
# ExaSearchBackend
# ---------------------------------------------------------------------------


class TestExaSearchBackend:
    """ExaSearchBackend のテスト."""

    def test_name属性はexa(self) -> None:
        backend = ExaSearchBackend(api_key="test-key")
        assert backend.name == "exa"

    def test_成功時にSearchResultリストを返す(self) -> None:
        response_data = {
            "results": [
                {
                    "title": "Python Docs",
                    "url": "https://docs.python.org",
                    "text": "Official docs",
                },
                {
                    "title": "Tutorial",
                    "url": "https://example.com",
                    "highlights": [{"text": "Learn Python"}],
                },
            ]
        }
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = (
            json.dumps(response_data).encode("utf-8")
        )

        with patch("urllib.request.urlopen", return_value=mock_response):
            backend = ExaSearchBackend(api_key="test-key")
            results = backend.search("python", 5, 25)

        assert len(results) == 2
        assert results[0]["title"] == "Python Docs"
        assert results[0]["url"] == "https://docs.python.org"
        assert results[1]["snippet"] == "Learn Python"

    def test_APIキー未設定時にToolExecutionErrorを送出する(self) -> None:
        backend = ExaSearchBackend(api_key="")
        with pytest.raises(ToolExecutionError, match="未設定"):
            backend.search("test", 5, 25)

    def test_HTTPエラー時にToolExecutionErrorを送出する(self) -> None:
        http_error = urllib.error.HTTPError(
            url="https://api.exa.ai/search",
            code=500,
            msg="Server Error",
            hdrs=MagicMock(),  # type: ignore[arg-type]
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            backend = ExaSearchBackend(api_key="test-key")
            with pytest.raises(ToolExecutionError, match="HTTP 500"):
                backend.search("test", 5, 25)

    def test_タイムアウト時にToolExecutionErrorを送出する(self) -> None:
        with patch("urllib.request.urlopen", side_effect=TimeoutError()):
            backend = ExaSearchBackend(api_key="test-key")
            with pytest.raises(ToolExecutionError, match="タイムアウト"):
                backend.search("test", 5, 25)


# ---------------------------------------------------------------------------
# DuckDuckGoSearchBackend
# ---------------------------------------------------------------------------


class TestDuckDuckGoSearchBackend:
    """DuckDuckGoSearchBackend のテスト."""

    def test_name属性はduckduckgo(self) -> None:
        backend = DuckDuckGoSearchBackend()
        assert backend.name == "duckduckgo"

    def test_HTMLパース成功(self) -> None:
        html = """
        <div class="result">
            <a class="result__a" href="https://example.com">
                Example Title
            </a>
            <a class="result__snippet">Example snippet text</a>
        </div>
        <div class="result">
            <a class="result__a" href="https://other.com">Other Title</a>
            <a class="result__snippet">Other snippet</a>
        </div>
        """
        results = _parse_ddg_html(html, 10)
        assert len(results) == 2
        assert results[0]["title"] == "Example Title"
        assert results[0]["url"] == "https://example.com"
        assert results[0]["snippet"] == "Example snippet text"

    def test_検索結果が空の場合(self) -> None:
        html = "<html><body>No results</body></html>"
        results = _parse_ddg_html(html, 10)
        assert results == []

    def test_max_resultsで件数を制限できる(self) -> None:
        html = """
        <a class="result__a" href="https://a.com">A</a>
        <a class="result__snippet">snip a</a>
        <a class="result__a" href="https://b.com">B</a>
        <a class="result__snippet">snip b</a>
        <a class="result__a" href="https://c.com">C</a>
        <a class="result__snippet">snip c</a>
        """
        results = _parse_ddg_html(html, 2)
        assert len(results) == 2

    def test_HTTPエラー時にToolExecutionErrorを送出する(self) -> None:
        http_error = urllib.error.HTTPError(
            url="https://html.duckduckgo.com/html/",
            code=503,
            msg="Service Unavailable",
            hdrs=MagicMock(),  # type: ignore[arg-type]
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            backend = DuckDuckGoSearchBackend()
            with pytest.raises(ToolExecutionError, match="HTTP 503"):
                backend.search("test", 5, 25)

    def test_タイムアウト時にToolExecutionErrorを送出する(self) -> None:
        with patch("urllib.request.urlopen", side_effect=TimeoutError()):
            backend = DuckDuckGoSearchBackend()
            with pytest.raises(ToolExecutionError, match="タイムアウト"):
                backend.search("test", 5, 25)

    def test_DDGリダイレクトURLからの実URL抽出(self) -> None:
        html = (
            '<a class="result__a" '
            'href="//duckduckgo.com/l/?uddg=https%3A%2F%2Freal.com&rut=abc">'
            "Real Title</a>"
            '<a class="result__snippet">Snippet</a>'
        )
        results = _parse_ddg_html(html, 10)
        assert len(results) == 1
        assert results[0]["url"] == "https://real.com"


# ---------------------------------------------------------------------------
# _format_search_results
# ---------------------------------------------------------------------------


class TestFormatSearchResults:
    """_format_search_results のテスト."""

    def test_結果をフォーマットできる(self) -> None:
        results: list[SearchResult] = [
            SearchResult(
                title="Test", url="https://test.com", snippet="desc"
            )
        ]
        output = _format_search_results("query", results)
        assert "Test" in output
        assert "https://test.com" in output

    def test_空結果の場合のメッセージ(self) -> None:
        output = _format_search_results("query", [])
        assert "見つかりませんでした" in output

    def test_フォールバック注記が含まれる(self) -> None:
        results: list[SearchResult] = [
            SearchResult(
                title="T", url="https://t.com", snippet=""
            )
        ]
        output = _format_search_results(
            "q", results, fallback_name="duckduckgo"
        )
        assert "フォールバック" in output
        assert "duckduckgo" in output


# ---------------------------------------------------------------------------
# WebSearchTool (統合テスト)
# ---------------------------------------------------------------------------


class TestWebSearchTool:
    """WebSearchTool のテスト."""

    def test_ツール名はwebsearch(self) -> None:
        tool = WebSearchTool()
        assert tool.name == "websearch"

    def test_デフォルト件数は5件(self) -> None:
        tool = WebSearchTool()
        assert tool.default_num_results == 5

    def test_デフォルトタイムアウトは25秒(self) -> None:
        tool = WebSearchTool()
        assert tool.timeout_seconds == 25

    def test_成功時に検索結果一覧を返す(self) -> None:
        response_data = {
            "results": [
                {
                    "title": "Python asyncio Documentation",
                    "url": "https://docs.python.org/asyncio",
                    "text": "Official asyncio documentation",
                },
            ]
        }

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = (
            json.dumps(response_data).encode("utf-8")
        )

        with patch("urllib.request.urlopen", return_value=mock_response):
            tool = WebSearchTool(api_key="test-api-key")
            result = tool._run("python asyncio")

        assert "Python asyncio Documentation" in result
        assert "https://docs.python.org/asyncio" in result

    def test_検索結果が空の場合のメッセージ(self) -> None:
        response_data: dict = {"results": []}
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = (
            json.dumps(response_data).encode("utf-8")
        )

        with patch("urllib.request.urlopen", return_value=mock_response):
            tool = WebSearchTool(api_key="test-api-key")
            result = tool._run("nonexistent query xyz")

        assert "見つかりませんでした" in result

    def test_プライマリ成功時にフォールバックしない(self) -> None:
        response_data = {
            "results": [
                {
                    "title": "Result",
                    "url": "https://example.com",
                    "text": "snippet",
                }
            ]
        }
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = (
            json.dumps(response_data).encode("utf-8")
        )

        with patch("urllib.request.urlopen", return_value=mock_response):
            tool = WebSearchTool(api_key="test-key")
            result = tool._run("test")

        assert "フォールバック" not in result
        assert "Result" in result

    def test_プライマリ失敗でセカンダリ成功(self) -> None:
        """Exa失敗→DuckDuckGo成功のフォールバック."""
        ddg_html = (
            '<a class="result__a" href="https://ddg.com">DDG Result</a>'
            '<a class="result__snippet">DDG snippet</a>'
        )
        mock_ddg = MagicMock()
        mock_ddg.__enter__ = MagicMock(return_value=mock_ddg)
        mock_ddg.__exit__ = MagicMock(return_value=False)
        mock_ddg.read.return_value = ddg_html.encode("utf-8")

        call_count = [0]

        def side_effect(*args, **kwargs):  # type: ignore[no-untyped-def]
            call_count[0] += 1
            if call_count[0] == 1:
                # Exa fails
                raise urllib.error.HTTPError(
                    url="https://api.exa.ai/search",
                    code=500,
                    msg="Error",
                    hdrs=MagicMock(),  # type: ignore[arg-type]
                    fp=None,
                )
            # DuckDuckGo succeeds
            return mock_ddg

        with patch("urllib.request.urlopen", side_effect=side_effect):
            tool = WebSearchTool(api_key="test-key")
            result = tool._run("test query")

        assert "フォールバック" in result
        assert "DDG Result" in result

    def test_全バックエンド失敗(self) -> None:
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            tool = WebSearchTool(api_key="test-key")
            result = tool._run("test query")

        assert "全ての検索バックエンドが失敗" in result

    def test_APIキー未設定でDuckDuckGoのみで動作する(self) -> None:
        ddg_html = (
            '<a class="result__a" href="https://ddg.com">DDG Only</a>'
            '<a class="result__snippet">Works without API key</a>'
        )
        mock_ddg = MagicMock()
        mock_ddg.__enter__ = MagicMock(return_value=mock_ddg)
        mock_ddg.__exit__ = MagicMock(return_value=False)
        mock_ddg.read.return_value = ddg_html.encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_ddg):
            tool = WebSearchTool(
                api_key="",
                search_backend_names=["exa", "duckduckgo"],
            )
            result = tool._run("test")

        # Exa fails (no API key), DuckDuckGo succeeds
        assert "DDG Only" in result
        assert "フォールバック" in result

    def test_fallback_disabled時はフォールバックしない(self) -> None:
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("fail"),
        ):
            tool = WebSearchTool(
                api_key="test-key", fallback_enabled=False
            )
            result = tool._run("test")

        assert "全ての検索バックエンドが失敗" in result

    def test_バックエンドなしの場合のメッセージ(self) -> None:
        tool = WebSearchTool(search_backend_names=[])
        result = tool._run("test")
        assert "バックエンドが設定されていません" in result


# ---------------------------------------------------------------------------
# WebFetchTool
# ---------------------------------------------------------------------------


class TestWebFetchTool:
    """WebFetchTool のテスト."""

    def test_ツール名はwebfetch(self) -> None:
        tool = WebFetchTool()
        assert tool.name == "webfetch"

    def test_無効なURLでSecurityErrorを発生させる(self) -> None:
        tool = WebFetchTool()
        with pytest.raises(SecurityError):
            tool._run("ftp://example.com")

    def test_スキームなしURLでSecurityErrorを発生させる(self) -> None:
        tool = WebFetchTool()
        with pytest.raises(SecurityError):
            tool._run("example.com")

    def test_Markdown形式でHTMLを返す(self) -> None:
        html_content = (
            b"<html><body><h1>Title</h1><p>Content</p></body></html>"
        )
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = html_content
        mock_response.headers.get.side_effect = (
            lambda key, default="": {
                "Content-Type": "text/html; charset=utf-8",
                "Content-Length": str(len(html_content)),
            }.get(key, default)
        )
        mock_response.status = 200

        with patch("urllib.request.urlopen", return_value=mock_response):
            tool = WebFetchTool()
            result = tool._run("https://example.com")

        assert "Title" in result
        assert "Content" in result

    def test_HTML形式を指定できる(self) -> None:
        html_content = b"<html><body><h1>Title</h1></body></html>"
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = html_content
        mock_response.headers.get.side_effect = (
            lambda key, default="": {
                "Content-Type": "text/html",
                "Content-Length": str(len(html_content)),
            }.get(key, default)
        )
        mock_response.status = 200

        with patch("urllib.request.urlopen", return_value=mock_response):
            tool = WebFetchTool()
            result = tool._run("https://example.com", format="html")

        assert "<h1>Title</h1>" in result

    def test_text形式を指定できる(self) -> None:
        html_content = (
            b"<html><body><h1>Title</h1><p>Content</p></body></html>"
        )
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = html_content
        mock_response.headers.get.side_effect = (
            lambda key, default="": {
                "Content-Type": "text/html",
                "Content-Length": str(len(html_content)),
            }.get(key, default)
        )
        mock_response.status = 200

        with patch("urllib.request.urlopen", return_value=mock_response):
            tool = WebFetchTool()
            result = tool._run("https://example.com", format="text")

        assert "Title" in result
        assert "<h1>" not in result

    def test_サイズ超過時にToolExecutionErrorを発生させる(self) -> None:
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.headers.get.side_effect = (
            lambda key, default="": {
                "Content-Type": "text/html",
                "Content-Length": str(10 * 1024 * 1024),
            }.get(key, default)
        )
        mock_response.status = 200

        with patch("urllib.request.urlopen", return_value=mock_response):
            tool = WebFetchTool(max_size_bytes=5 * 1024 * 1024)
            with pytest.raises(ToolExecutionError, match="上限"):
                tool._run("https://example.com")

    def test_タイムアウト時にToolExecutionErrorを発生させる(self) -> None:
        with patch(
            "urllib.request.urlopen", side_effect=TimeoutError()
        ):
            tool = WebFetchTool()
            with pytest.raises(ToolExecutionError, match="タイムアウト"):
                tool._run("https://example.com")

    def test_Cloudflareブロック時にToolExecutionErrorを発生させる(
        self,
    ) -> None:
        http_error = urllib.error.HTTPError(
            url="https://example.com",
            code=403,
            msg="Forbidden",
            hdrs=MagicMock(),  # type: ignore[arg-type]
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            tool = WebFetchTool()
            with pytest.raises(ToolExecutionError, match="ブロック"):
                tool._run("https://example.com")

    def test_HTTPエラー404時にToolExecutionErrorを発生させる(self) -> None:
        http_error = urllib.error.HTTPError(
            url="https://example.com/notfound",
            code=404,
            msg="Not Found",
            hdrs=MagicMock(),  # type: ignore[arg-type]
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            tool = WebFetchTool()
            with pytest.raises(ToolExecutionError, match="HTTP 404"):
                tool._run("https://example.com/notfound")

    def test_接続失敗時にToolExecutionErrorを発生させる(self) -> None:
        url_error = urllib.error.URLError("Connection refused")
        with patch("urllib.request.urlopen", side_effect=url_error):
            tool = WebFetchTool()
            with pytest.raises(ToolExecutionError, match="接続に失敗"):
                tool._run("https://example.com")

    def test_デフォルトタイムアウトは30秒(self) -> None:
        tool = WebFetchTool()
        assert tool.timeout_seconds == 30

    def test_デフォルト最大サイズは5MB(self) -> None:
        tool = WebFetchTool()
        assert tool.max_size_bytes == 5 * 1024 * 1024
