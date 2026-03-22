"""設定管理のテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from myagent.infra.config import (
    AppConfig,
    LLMConfig,
    MCPConfig,
    MCPServerConfig,
    PluginConfig,
    SkillConfig,
    WebSearchConfig,
    load_config,
    merge_configs,
    save_config,
)
from myagent.infra.errors import ConfigError


class TestLLMConfigのデフォルト値:
    """LLMConfig のデフォルト値を検証する."""

    def test_デフォルトプロバイダはopenai(self) -> None:
        config = LLMConfig()
        assert config.provider == "openai"

    def test_デフォルトモデルはgpt5_nano(self) -> None:
        config = LLMConfig()
        assert config.model == "gpt-5-nano"

    def test_デフォルトフォールバックはgemini(self) -> None:
        config = LLMConfig()
        assert config.fallback_provider == "gemini"
        assert config.fallback_model == "gemini-3.1-flash-lite-preview"

    def test_デフォルトmax_retriesは3(self) -> None:
        config = LLMConfig()
        assert config.max_retries == 3


class TestAppConfigのデフォルト値:
    """AppConfig のデフォルト値を検証する."""

    def test_デフォルトで全設定が初期化される(self) -> None:
        config = AppConfig()
        assert config.llm.provider == "openai"
        assert config.tool.confirmation_level == "normal"
        assert config.agent.max_loops == 20
        assert config.openai_api_key == ""
        assert config.google_api_key == ""

    def test_context_window_tokensのデフォルトは128000(self) -> None:
        from myagent.infra.config import AgentConfig

        config = AgentConfig()
        assert config.context_window_tokens == 128_000

    def test_context_window_tokensをカスタム値で設定できる(self) -> None:
        from myagent.infra.config import AgentConfig

        config = AgentConfig(context_window_tokens=50_000)
        assert config.context_window_tokens == 50_000


class TestAgentConfigの並列ワーカー設定:
    """AgentConfig の max_parallel_workers を検証する."""

    def test_デフォルトmax_parallel_workersは3(self) -> None:
        from myagent.infra.config import AgentConfig

        config = AgentConfig()
        assert config.max_parallel_workers == 3

    def test_max_parallel_workersを1から10の範囲で設定できる(self) -> None:
        from myagent.infra.config import AgentConfig

        config = AgentConfig(max_parallel_workers=1)
        assert config.max_parallel_workers == 1
        config = AgentConfig(max_parallel_workers=10)
        assert config.max_parallel_workers == 10

    def test_max_parallel_workersが範囲外でバリデーションエラー(self) -> None:
        from pydantic import ValidationError

        from myagent.infra.config import AgentConfig

        with pytest.raises(ValidationError):
            AgentConfig(max_parallel_workers=0)
        with pytest.raises(ValidationError):
            AgentConfig(max_parallel_workers=11)

    def test_AppConfigにmax_parallel_workersが含まれる(self) -> None:
        config = AppConfig()
        assert config.agent.max_parallel_workers == 3


class TestSkillConfigのデフォルト値:
    """SkillConfig のデフォルト値を検証する."""

    def test_デフォルトproject_skills_dirは設定されている(self) -> None:
        config = SkillConfig()
        assert config.project_skills_dir == ".myagent/skills"

    def test_デフォルトglobal_skills_dirは空文字(self) -> None:
        config = SkillConfig()
        assert config.global_skills_dir == ""

    def test_AppConfigにskillフィールドがある(self) -> None:
        config = AppConfig()
        assert isinstance(config.skill, SkillConfig)
        assert config.skill.project_skills_dir == ".myagent/skills"


class TestPluginConfigのデフォルト値:
    """PluginConfig のデフォルト値を検証する."""

    def test_デフォルトcache_dirは空文字(self) -> None:
        config = PluginConfig()
        assert config.cache_dir == ""

    def test_デフォルトdata_dirは空文字(self) -> None:
        config = PluginConfig()
        assert config.data_dir == ""

    def test_デフォルトenabled_pluginsは空リスト(self) -> None:
        config = PluginConfig()
        assert config.enabled_plugins == []

    def test_デフォルトplugin_dirsは空リスト(self) -> None:
        config = PluginConfig()
        assert config.plugin_dirs == []

    def test_AppConfigにpluginフィールドがある(self) -> None:
        config = AppConfig()
        assert isinstance(config.plugin, PluginConfig)
        assert config.plugin.enabled_plugins == []


class Testload_config:
    """load_config 関数のテスト."""

    def test_存在しないファイルからデフォルト設定を生成する(
        self, tmp_path: Path
    ) -> None:
        config = load_config(tmp_path / "nonexistent.toml")
        assert config.llm.provider == "openai"

    def test_有効なtomlファイルから設定を読み込む(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[llm]\nprovider = "gemini"\nmodel = "gemini-2.5-pro"\n'
            "temperature = 0.5\nmax_retries = 2\n",
            encoding="utf-8",
        )
        config = load_config(config_path)
        assert config.llm.provider == "gemini"
        assert config.llm.model == "gemini-2.5-pro"

    def test_不正なtomlファイルでConfigErrorが発生する(self, tmp_path: Path) -> None:
        config_path = tmp_path / "broken.toml"
        config_path.write_bytes(b"\x00\x01invalid toml")
        with pytest.raises(ConfigError):
            load_config(config_path)

    def test_環境変数でAPIキーを上書きする(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "google-test-key")
        config = load_config(tmp_path / "nonexistent.toml")
        assert config.openai_api_key == "sk-test-key"
        assert config.google_api_key == "google-test-key"


class Testsave_config:
    """save_config 関数のテスト."""

    def test_設定をファイルに保存できる(self, tmp_path: Path) -> None:
        config = AppConfig()
        config_path = tmp_path / "output.toml"
        save_config(config, config_path)
        assert config_path.exists()

    def test_APIキーはファイルに保存されない(self, tmp_path: Path) -> None:
        config = AppConfig(openai_api_key="secret", google_api_key="secret2")
        config_path = tmp_path / "output.toml"
        save_config(config, config_path)
        content = config_path.read_text(encoding="utf-8")
        assert "secret" not in content

    def test_保存した設定を再度読み込める(self, tmp_path: Path) -> None:
        original = AppConfig()
        original.llm.provider = "gemini"
        original.llm.model = "gemini-2.5-pro"
        config_path = tmp_path / "roundtrip.toml"
        save_config(original, config_path)
        loaded = load_config(config_path)
        assert loaded.llm.provider == "gemini"
        assert loaded.llm.model == "gemini-2.5-pro"


class TestMCPServerConfigのバリデーション:
    """MCPServerConfig のバリデーションをテストする."""

    def test_stdioサーバー設定が作成できる(self) -> None:
        config = MCPServerConfig(
            name="github",
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
        )
        assert config.name == "github"
        assert config.transport == "stdio"
        assert config.command == "npx"

    def test_httpサーバー設定が作成できる(self) -> None:
        config = MCPServerConfig(
            name="remote",
            transport="http",
            url="http://localhost:8080",
        )
        assert config.transport == "http"
        assert config.url == "http://localhost:8080"

    def test_デフォルトtimeoutは30秒(self) -> None:
        config = MCPServerConfig(name="test", transport="stdio")
        assert config.timeout == 30


class TestAppConfigのMCP設定:
    """AppConfig に MCPConfig が統合されていることを検証する."""

    def test_デフォルトでmcpが初期化される(self) -> None:
        config = AppConfig()
        assert isinstance(config.mcp, MCPConfig)
        assert config.mcp.servers == []

    def test_MCPサーバーをAppConfigに設定できる(self) -> None:
        config = AppConfig(
            mcp=MCPConfig(
                servers=[
                    MCPServerConfig(name="github", transport="stdio", command="npx")
                ]
            )
        )
        assert len(config.mcp.servers) == 1
        assert config.mcp.servers[0].name == "github"

    def test_MCP設定をファイルに保存して読み込める(self, tmp_path: Path) -> None:
        original = AppConfig(
            mcp=MCPConfig(
                servers=[
                    MCPServerConfig(
                        name="test",
                        transport="stdio",
                        command="cmd",
                        timeout=60,
                    )
                ]
            )
        )
        config_path = tmp_path / "mcp_config.toml"
        save_config(original, config_path)
        loaded = load_config(config_path)
        assert len(loaded.mcp.servers) == 1
        assert loaded.mcp.servers[0].name == "test"
        assert loaded.mcp.servers[0].timeout == 60


class TestWebSearchConfigのフォールバック設定:
    """WebSearchConfig のフォールバック設定テスト."""

    def test_デフォルトでfallback_enabledはTrue(self) -> None:
        config = WebSearchConfig()
        assert config.fallback_enabled is True

    def test_デフォルトのsearch_backendsはexa_duckduckgo(
        self,
    ) -> None:
        config = WebSearchConfig()
        assert config.search_backends == [
            "exa",
            "duckduckgo",
        ]

    def test_fallback_enabledをFalseに設定できる(self) -> None:
        config = WebSearchConfig(fallback_enabled=False)
        assert config.fallback_enabled is False

    def test_search_backendsをカスタマイズできる(self) -> None:
        config = WebSearchConfig(
            search_backends=["duckduckgo"]
        )
        assert config.search_backends == ["duckduckgo"]

    def test_AppConfigにフォールバック設定が含まれる(self) -> None:
        config = AppConfig()
        assert config.web_search.fallback_enabled is True
        assert "exa" in config.web_search.search_backends

    def test_save_load_でフォールバック設定が保持される(
        self, tmp_path: Path
    ) -> None:
        original = AppConfig(
            web_search=WebSearchConfig(
                fallback_enabled=False,
                search_backends=["duckduckgo"],
            )
        )
        config_path = tmp_path / "fb_config.toml"
        save_config(original, config_path)
        loaded = load_config(config_path)
        assert loaded.web_search.fallback_enabled is False
        assert loaded.web_search.search_backends == [
            "duckduckgo",
        ]


class Testmerge_configs:
    """merge_configs 関数のテスト."""

    def test_空のoverrideはbaseをそのまま返す(self) -> None:
        base = {"llm": {"provider": "openai", "model": "gpt-5-nano"}}
        result = merge_configs(base, {})
        assert result == base

    def test_ネストされたdictを再帰マージする(self) -> None:
        base = {"llm": {"provider": "openai", "model": "gpt-5-nano"}}
        override = {"llm": {"model": "gemini-2.5-pro"}}
        result = merge_configs(base, override)
        assert result["llm"]["provider"] == "openai"
        assert result["llm"]["model"] == "gemini-2.5-pro"

    def test_リスト値は上書きされる(self) -> None:
        base = {"tool": {"allowed_directories": ["/home"]}}
        override = {"tool": {"allowed_directories": ["/tmp", "/var"]}}
        result = merge_configs(base, override)
        assert result["tool"]["allowed_directories"] == ["/tmp", "/var"]

    def test_overrideに存在しないキーはbaseの値を保持(self) -> None:
        base = {"llm": {"provider": "openai"}, "agent": {"max_loops": 20}}
        override = {"llm": {"provider": "gemini"}}
        result = merge_configs(base, override)
        assert result["agent"]["max_loops"] == 20

    def test_overrideにのみ存在するキーが追加される(self) -> None:
        base = {"llm": {"provider": "openai"}}
        override = {"agent": {"max_loops": 10}}
        result = merge_configs(base, override)
        assert result["agent"]["max_loops"] == 10
        assert result["llm"]["provider"] == "openai"

    def test_baseを変更しない(self) -> None:
        base = {"llm": {"provider": "openai"}}
        override = {"llm": {"provider": "gemini"}}
        merge_configs(base, override)
        assert base["llm"]["provider"] == "openai"


class Testload_configのプロジェクト設定マージ:
    """load_config のプロジェクトローカル設定マージのテスト."""

    def test_プロジェクト設定がグローバル設定にマージされる(
        self, tmp_path: Path
    ) -> None:
        # グローバル設定
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        global_config = global_dir / "config.toml"
        global_config.write_text(
            '[llm]\nprovider = "openai"\nmodel = "gpt-5-nano"\n',
            encoding="utf-8",
        )

        # プロジェクトローカル設定
        project_dir = tmp_path / "project"
        (project_dir / ".myagent").mkdir(parents=True)
        project_config = project_dir / ".myagent" / "config.toml"
        project_config.write_text(
            '[llm]\nmodel = "gemini-2.5-pro"\nprovider = "gemini"\n',
            encoding="utf-8",
        )

        # monkeypatch でグローバルパスを差し替え
        import myagent.infra.config as config_mod

        original_path = config_mod.DEFAULT_CONFIG_PATH
        try:
            config_mod.DEFAULT_CONFIG_PATH = global_config
            config = load_config(project_config_dir=project_dir)
            assert config.llm.provider == "gemini"
            assert config.llm.model == "gemini-2.5-pro"
        finally:
            config_mod.DEFAULT_CONFIG_PATH = original_path

    def test_プロジェクト設定が存在しない場合グローバル設定のみ使用(
        self, tmp_path: Path
    ) -> None:
        project_dir = tmp_path / "empty_project"
        project_dir.mkdir()
        config = load_config(
            tmp_path / "nonexistent.toml",
        )
        assert config.llm.provider == "openai"

    def test_config_path指定時はプロジェクト設定マージをスキップ(
        self, tmp_path: Path
    ) -> None:
        # 明示的設定ファイル
        explicit_config = tmp_path / "explicit.toml"
        explicit_config.write_text(
            '[llm]\nprovider = "openai"\nmodel = "explicit-model"\n',
            encoding="utf-8",
        )

        # プロジェクト設定（マージされないはず）
        project_dir = tmp_path / "project"
        (project_dir / ".myagent").mkdir(parents=True)
        project_config = project_dir / ".myagent" / "config.toml"
        project_config.write_text(
            '[llm]\nmodel = "should-not-appear"\n',
            encoding="utf-8",
        )

        config = load_config(
            config_path=explicit_config,
            project_config_dir=project_dir,
        )
        assert config.llm.model == "explicit-model"
