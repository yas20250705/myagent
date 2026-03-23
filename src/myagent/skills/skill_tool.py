"""LLM駆動スキル選択のための activate_skill ツール."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import model_validator


class ActivateSkillTool(BaseTool):
    """スキルをアクティベートしてスキルボディを返すツール.

    LLMがユーザーの指示内容に基づいて自律的にスキルを選択・アクティベートするために
    呼び出すツール。スキルボディがツール結果としてLLMのコンテキストに注入される。
    """

    name: str = "activate_skill"
    description: str = (
        "利用可能なスキルの中から指定したスキルをアクティベートし、"
        "そのスキルの詳細な指示内容を取得します。"
        "ユーザーの指示が特定のスキルに関連していると判断した場合に呼び出してください。"
        "引数: skill_name (str) - アクティベートするスキル名（例: 'skill-creator'）"
    )
    skill_manager: Any  # SkillManager: Pydantic v2との互換性のため Any を使用

    @model_validator(mode="before")
    @classmethod
    def _validate_skill_manager(cls, values: dict[str, Any]) -> dict[str, Any]:
        if "skill_manager" not in values or values["skill_manager"] is None:
            raise ValueError("skill_manager は必須です")
        return values

    def _run(self, skill_name: str) -> str:
        """スキルをアクティベートしてスキルボディを返す.

        Args:
            skill_name: アクティベートするスキル名。

        Returns:
            スキルボディのMarkdownテキスト。見つからない場合はエラーメッセージ。
        """
        skill = self.skill_manager.activate(skill_name)
        if skill is None:
            available = [
                m.name
                for m in self.skill_manager.get_all_metadata()
                if not m.disable_model_invocation
            ]
            available_str = ", ".join(available) if available else "（なし）"
            return (
                f"スキル '{skill_name}' が見つかりません。"
                f"利用可能なスキル: {available_str}"
            )

        return f"# アクティブスキル: {skill.meta.name}\n\n{skill.body}"

    async def _arun(self, skill_name: str) -> str:
        """非同期版（同期実装に委譲）."""
        return self._run(skill_name)
