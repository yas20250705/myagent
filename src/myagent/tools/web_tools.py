"""Web検索・Webページ取得ツール群.

WebSearchTool と WebFetchTool を提供する。
WebSearchTool は複数の検索バックエンドをフォールバック付きで使用する。
WebFetchTool は指定URLのHTMLを取得してMarkdown等に変換する。
"""

from __future__ import annotations

import html as html_module
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

from langchain_core.tools import BaseTool
from pydantic import ConfigDict, Field

from myagent.infra.errors import SecurityError, ToolExecutionError

logger = logging.getLogger(__name__)

_MAX_FETCH_TIMEOUT = 120
_ALLOWED_SCHEMES = ("http://", "https://")


def _validate_url(url: str) -> None:
    """URLが許可されたスキームで始まるか検証する."""
    if not any(url.startswith(s) for s in _ALLOWED_SCHEMES):
        msg = (
            "URLは http:// または https:// で"
            f"始まる必要があります: {url}"
        )
        raise SecurityError(msg)


# ---------------------------------------------------------------------------
# 検索バックエンド抽象
# ---------------------------------------------------------------------------


class SearchResult(TypedDict):
    """検索結果1件を表す辞書型."""

    title: str
    url: str
    snippet: str


@runtime_checkable
class SearchBackend(Protocol):
    """検索バックエンドの共通インターフェース."""

    @property
    def name(self) -> str: ...

    def search(
        self, query: str, num_results: int, timeout: int
    ) -> list[SearchResult]: ...


# ---------------------------------------------------------------------------
# Exa AI 検索バックエンド
# ---------------------------------------------------------------------------


class ExaSearchBackend:
    """Exa AI REST API を使用する検索バックエンド."""

    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://api.exa.ai/search",
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint

    @property
    def name(self) -> str:
        return "exa"

    def search(
        self, query: str, num_results: int, timeout: int
    ) -> list[SearchResult]:
        """Exa AI API で検索を実行する.

        Args:
            query: 検索クエリ。
            num_results: 取得件数。
            timeout: タイムアウト秒数。

        Returns:
            検索結果リスト。

        Raises:
            ToolExecutionError: API呼び出しに失敗した場合。
        """
        if not self._api_key:
            logger.warning("Exa APIキーが未設定です")
            msg = "Exa APIキーが未設定です"
            raise ToolExecutionError(msg, "websearch")

        request_body: dict[str, Any] = {
            "query": query,
            "type": "auto",
            "numResults": num_results,
            "contents": {
                "highlights": {"maxCharacters": 4000},
            },
        }
        payload = json.dumps(request_body).encode("utf-8")

        req = urllib.request.Request(
            self._endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
        except TimeoutError as e:
            msg = f"Exa検索がタイムアウトしました ({timeout}秒)"
            raise ToolExecutionError(msg, "websearch") from e
        except urllib.error.HTTPError as e:
            msg = f"Exa APIエラー: HTTP {e.code} {e.reason}"
            raise ToolExecutionError(msg, "websearch") from e
        except urllib.error.URLError as e:
            msg = f"Exa APIへの接続に失敗しました: {e.reason}"
            raise ToolExecutionError(msg, "websearch") from e

        try:
            data: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError as e:
            msg = f"Exaレスポンスのパースに失敗: {e}"
            raise ToolExecutionError(msg, "websearch") from e

        results: list[SearchResult] = []
        for item in data.get("results", []):
            snippet = ""
            highlights = item.get("highlights")
            if isinstance(highlights, list) and highlights:
                hl = highlights[0]
                if isinstance(hl, dict):
                    snippet = hl.get("text", "")
                else:
                    snippet = str(hl)
            if not snippet:
                snippet = item.get(
                    "text", item.get("snippet", "")
                )
            results.append(
                SearchResult(
                    title=item.get("title", "(タイトルなし)"),
                    url=item.get("url", ""),
                    snippet=snippet,
                )
            )
        return results


# ---------------------------------------------------------------------------
# DuckDuckGo 検索バックエンド
# ---------------------------------------------------------------------------

_DDG_ENDPOINT = "https://html.duckduckgo.com/html/"


class DuckDuckGoSearchBackend:
    """DuckDuckGo HTML版を使用する検索バックエンド.

    APIキー不要で利用可能。
    """

    @property
    def name(self) -> str:
        return "duckduckgo"

    def search(
        self, query: str, num_results: int, timeout: int
    ) -> list[SearchResult]:
        """DuckDuckGo HTML版で検索を実行する.

        Args:
            query: 検索クエリ。
            num_results: 取得件数。
            timeout: タイムアウト秒数。

        Returns:
            検索結果リスト。

        Raises:
            ToolExecutionError: 検索に失敗した場合。
        """
        form_data = urllib.parse.urlencode({"q": query}).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            _DDG_ENDPOINT,
            data=form_data,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; MyAgent/1.0)"
                ),
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                ),
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                req, timeout=timeout
            ) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except TimeoutError as e:
            msg = f"DuckDuckGo検索がタイムアウト ({timeout}秒)"
            raise ToolExecutionError(msg, "websearch") from e
        except urllib.error.HTTPError as e:
            msg = (
                f"DuckDuckGo APIエラー: HTTP {e.code} {e.reason}"
            )
            raise ToolExecutionError(msg, "websearch") from e
        except urllib.error.URLError as e:
            msg = f"DuckDuckGoへの接続に失敗: {e.reason}"
            raise ToolExecutionError(msg, "websearch") from e

        return _parse_ddg_html(html, num_results)


def _parse_ddg_html(
    html: str, max_results: int
) -> list[SearchResult]:
    """DuckDuckGo HTML版のレスポンスから検索結果をパースする."""
    results: list[SearchResult] = []

    # result__a タグからタイトルとURLを抽出
    # result__snippet タグからスニペットを抽出
    link_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>'
        r"(.*?)</a>",
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (raw_url, raw_title) in enumerate(links):
        if len(results) >= max_results:
            break

        title = _strip_html_tags(raw_title).strip()
        url = _extract_ddg_url(raw_url)
        snippet = ""
        if i < len(snippets):
            snippet = _strip_html_tags(snippets[i]).strip()

        if title and url:
            results.append(
                SearchResult(
                    title=title, url=url, snippet=snippet
                )
            )

    return results


def _extract_ddg_url(raw_url: str) -> str:
    """DuckDuckGoのリダイレクトURLから実際のURLを抽出する."""
    # DuckDuckGoは //duckduckgo.com/l/?uddg=<encoded_url>&... 形式
    if "uddg=" in raw_url:
        parsed = urllib.parse.urlparse(raw_url)
        params = urllib.parse.parse_qs(parsed.query)
        uddg = params.get("uddg", [""])
        if uddg and uddg[0]:
            return uddg[0]
    # リダイレクトなしの場合
    if raw_url.startswith("//"):
        return "https:" + raw_url
    return raw_url


def _strip_html_tags(text: str) -> str:
    """HTMLタグを除去してプレーンテキストを返す."""
    clean = re.sub(r"<[^>]+>", "", text)
    return html_module.unescape(clean)


# ---------------------------------------------------------------------------
# WebSearchTool
# ---------------------------------------------------------------------------


class WebSearchTool(BaseTool):
    """フォールバック対応のWeb検索ツール.

    複数の検索バックエンドを順に試行し、
    最初に成功したバックエンドの結果を返す。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "websearch"
    description: str = (
        "Web検索を実行する。queryに検索クエリ、"
        "num_resultsに返す結果件数"
        "（デフォルト: 5件、最大50件）を指定する。"
        "\n\n【用途】最新のドキュメント、APIリファレンス、技術記事、エラーの解決方法など、"
        "外部のWeb情報を検索する際に使用する。"
        "\n\n【プロジェクト内検索優先ルール】"
        "プロジェクト内のファイルやコードに関する情報は、まずgrep_search/glob_searchで検索すること。"
        "プロジェクト内で見つからない場合にのみwebsearchを使う。"
        "\n\n【検索クエリの品質ガイド】"
        "具体的で詳細なクエリを記述すること。"
        "悪い例: 'Python エラー'（曖昧すぎる）。"
        "良い例: 'Python TypeError cannot unpack "
        "non-sequence NoneType'"
        "（具体的なエラーメッセージを含む）。"
        "良い例: 'LangChain BaseTool custom "
        "description length limit'"
        "（ライブラリ名+具体的なトピック）。"
        "\n\n【出力形式】"
        "各結果はタイトル、URL、概要（スニペット）を含む。"
        "結果の詳細を確認したい場合はwebfetchでURLを取得すること。"
        "\n\n【エッジケース】"
        "検索結果が0件の場合はその旨のメッセージを返す。"
        "バックエンドが応答しない場合は自動フォールバックする。"
        "\n\n【フォールバック】"
        "プライマリ検索バックエンドが失敗した場合、自動的にフォールバックバックエンドで再検索する。"
        "全バックエンドが失敗した場合はエラーメッセージを返す。その場合、websearchを再呼び出しせず、検索なしで回答すること。"
        "\n\n【アンチパターン】"
        "プロジェクト内の情報を探すためにwebsearchを使ってはいけない（grep_search/glob_searchを先に使う）。"
        "曖昧な検索クエリを使ってはいけない。"
    )
    api_key: str = ""
    endpoint: str = "https://api.exa.ai/search"
    timeout_seconds: int = Field(default=25, ge=1, le=120)
    default_num_results: int = Field(default=5, ge=1, le=50)
    fallback_enabled: bool = True
    search_backend_names: list[str] = Field(
        default_factory=lambda: ["exa", "duckduckgo"]
    )

    def _build_backends(self) -> list[SearchBackend]:
        """設定に基づいてバックエンドリストを構築する."""
        backends: list[SearchBackend] = []
        for name in self.search_backend_names:
            if name == "exa":
                backends.append(
                    ExaSearchBackend(
                        api_key=self.api_key,
                        endpoint=self.endpoint,
                    )
                )
            elif name == "duckduckgo":
                backends.append(DuckDuckGoSearchBackend())
        return backends

    def _run(
        self,
        query: str,
        num_results: int | None = None,
        **_kwargs: Any,
    ) -> str:
        """Web検索を実行して結果一覧を返す."""
        n = (
            num_results
            if num_results is not None
            else self.default_num_results
        )
        backends = self._build_backends()

        if not backends:
            return (
                "Web検索バックエンドが設定されていません。"
            )

        last_error: str = ""

        for i, backend in enumerate(backends):
            is_fallback = i > 0
            try:
                results = backend.search(
                    query, n, self.timeout_seconds
                )
                if is_fallback:
                    logger.warning(
                        "フォールバック検索を使用: %s",
                        backend.name,
                    )
                return _format_search_results(
                    query,
                    results,
                    fallback_name=(
                        backend.name if is_fallback else None
                    ),
                )
            except (ToolExecutionError, Exception) as e:
                last_error = str(e)
                logger.warning(
                    "検索バックエンド '%s' が失敗: %s",
                    backend.name,
                    last_error,
                )
                if not self.fallback_enabled:
                    break

        return (
            f"全ての検索バックエンドが失敗しました。"
            f"\n最後のエラー: {last_error}\n"
            "このツールを再度呼び出さず、"
            "検索なしで回答してください。"
        )


def _format_search_results(
    query: str,
    results: list[SearchResult],
    fallback_name: str | None = None,
) -> str:
    """検索結果を整形された文字列に変換する."""
    if not results:
        return f"'{query}' の検索結果が見つかりませんでした。"

    lines: list[str] = []
    if fallback_name:
        lines.append(
            f"(注: フォールバック検索 [{fallback_name}] "
            "を使用した結果です)\n"
        )
    lines.append(f"検索結果: '{query}'\n")

    for i, result in enumerate(results, 1):
        title = result["title"]
        url = result["url"]
        snippet = result["snippet"]
        lines.append(f"{i}. **{title}**")
        lines.append(f"   URL: {url}")
        if snippet:
            short = (
                snippet[:300] + "..."
                if len(snippet) > 300
                else snippet
            )
            lines.append(f"   概要: {short}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# WebFetchTool
# ---------------------------------------------------------------------------


class WebFetchTool(BaseTool):
    """指定URLのWebページを取得してMarkdown等に変換するツール."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "webfetch"
    description: str = (
        "指定URLのWebページを取得してMarkdown等に変換する。urlにアクセス先URL、formatに出力形式を指定する。"
        "\n\n【パラメータ】"
        "url: 取得するWebページのURL。"
        "format: 出力形式を選択（デフォルト: 'markdown'）。"
        "  'markdown' → HTML をMarkdownに変換して返す"
        "（ドキュメント・記事の可読性が最も高い）。"
        "  'text' → HTMLタグを除去したプレーンテキストで返す（構造が不要な場合）。"
        "  'html' → 生のHTMLで返す（DOM構造やスタイルの確認が必要な場合）。"
        "\n\n【URL取得元の制約】"
        "URLはユーザーが提供したもの、またはwebsearchの結果から取得したもののみ使用すること。"
        "URLを推測・生成してはいけない（存在しないページにアクセスする原因になる）。"
        "\n\n【エッジケース】"
        "アクセス不可のURLの場合はエラーを返す。"
        "タイムアウト（デフォルト30秒）超過時はエラーを返す。"
        "サイズ制限超過時は先頭部分のみ返す。"
        "\n\n【制限事項】"
        "大きなページはmax_size_bytes（デフォルト5MB）で制限され、超過分は切り捨てられる。"
        "タイムアウトはデフォルト30秒。応答が遅いサイトではタイムアウトエラーになる場合がある。"
        "\n\n【アンチパターン】"
        "URLを推測・生成して使ってはいけない（ユーザー提供 or websearch結果のみ）。"
        "プロジェクト内のファイルを取得するためにwebfetchを使ってはいけない（read_fileを使う）。"
    )
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_size_bytes: int = Field(default=5 * 1024 * 1024, ge=1)

    def _run(
        self,
        url: str,
        format: Literal["markdown", "text", "html"] = "markdown",
        **_kwargs: Any,
    ) -> str:
        """URLのWebページを取得して指定形式に変換して返す."""
        _validate_url(url)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; MyAgent/1.0; "
                    "+https://github.com/myagent)"
                ),
                "Accept": "text/html,application/xhtml+xml,*/*",
            },
        )

        try:
            with urllib.request.urlopen(
                req, timeout=self.timeout_seconds
            ) as resp:
                # レスポンスサイズチェック
                cl_str = resp.headers.get(
                    "Content-Length", ""
                )
                if cl_str:
                    try:
                        cl = int(cl_str)
                        if cl > self.max_size_bytes:
                            max_mb = self.max_size_bytes / (
                                1024 * 1024
                            )
                            size_mb = cl / (1024 * 1024)
                            msg = (
                                f"レスポンスサイズが上限"
                                f" ({max_mb:.1f}MB) を"
                                f"超えています: {size_mb:.1f}MB"
                            )
                            raise ToolExecutionError(
                                msg, self.name
                            )
                    except ValueError:
                        pass

                # 最大サイズ分だけ読み込む
                raw = resp.read(self.max_size_bytes + 1)
                if len(raw) > self.max_size_bytes:
                    max_mb = self.max_size_bytes / (1024 * 1024)
                    msg = (
                        f"レスポンスサイズが上限"
                        f" ({max_mb:.1f}MB) を超えています"
                    )
                    raise ToolExecutionError(msg, self.name)

                # 文字コード判定
                ct: str = resp.headers.get(
                    "Content-Type"
                ) or ""
                charset = _extract_charset(ct)
                html_content: str = raw.decode(
                    charset, errors="replace"
                )
                http_status: int = resp.status

        except ToolExecutionError:
            raise
        except TimeoutError as e:
            msg = (
                f"Webページ取得がタイムアウトしました"
                f" ({self.timeout_seconds}秒): {url}"
            )
            raise ToolExecutionError(msg, self.name) from e
        except urllib.error.HTTPError as e:
            if e.code in (403, 503):
                msg = (
                    f"アクセスがブロックされました"
                    f" (HTTP {e.code}): {url}\n"
                    "Cloudflare等のセキュリティシステムにより"
                    "アクセスが制限されている可能性があります。"
                )
            else:
                msg = (
                    f"Webページ取得エラー:"
                    f" HTTP {e.code} {e.reason}: {url}"
                )
            raise ToolExecutionError(msg, self.name) from e
        except urllib.error.URLError as e:
            msg = (
                f"Webページへの接続に失敗しました:"
                f" {e.reason}: {url}"
            )
            raise ToolExecutionError(msg, self.name) from e

        if http_status >= 400:
            msg = (
                f"Webページ取得エラー:"
                f" HTTP {http_status}: {url}"
            )
            raise ToolExecutionError(msg, self.name)

        if format == "html":
            return html_content

        if format == "text":
            return _html_to_text(html_content)

        # デフォルト: markdown
        return _html_to_markdown(html_content, url)


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


def _extract_charset(content_type: str) -> str:
    """Content-Type ヘッダーから文字コードを抽出する."""
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            charset = part[len("charset=") :].strip().strip('"')
            return charset if charset else "utf-8"
    return "utf-8"


def _html_to_text(html: str) -> str:
    """HTMLからプレーンテキストを抽出する."""
    try:
        import html2text as h2t

        converter = h2t.HTML2Text()
        converter.ignore_links = True
        converter.ignore_images = True
        converter.body_width = 0
        return converter.handle(html)
    except ImportError:
        return _simple_strip_tags(html)
    except Exception:
        return _simple_strip_tags(html)


def _html_to_markdown(html: str, url: str = "") -> str:
    """HTMLをMarkdown形式に変換する."""
    try:
        import html2text as h2t

        converter = h2t.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = False
        converter.body_width = 0
        converter.baseurl = url
        return converter.handle(html)
    except ImportError:
        return _simple_strip_tags(html)
    except Exception:
        return _simple_strip_tags(html)


def _simple_strip_tags(html: str) -> str:
    """html2text が利用できない場合の簡易HTMLタグ除去."""
    # scriptとstyleブロックを削除
    text = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # タグを削除
    text = re.sub(r"<[^>]+>", "", text)
    # HTMLエンティティを変換
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    text = text.replace("&nbsp;", " ")
    # 連続した空行を整理
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
