"""設定管理のテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from myagent.infra.config import AppConfig, LLMConfig, load_config, save_config
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


class Testload_config:
    """load_config 関数のテスト."""

    def test_存在しないファイルからデフォルト設定を生成する(self, tmp_path: Path) -> None:
        config = load_config(tmp_path / "nonexistent.toml")
        assert config.llm.provider == "openai"

    def test_有効なtomlファイルから設定を読み込む(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[llm]\nprovider = "gemini"\nmodel = "gemini-2.5-pro"\n'
            'temperature = 0.5\nmax_retries = 2\n',
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
