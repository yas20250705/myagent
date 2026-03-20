"""Planner モジュール.

ユーザーの指示をサブタスクに分解し、実行計画を生成する。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from myagent.agent.state import SubTask

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM_PROMPT = (
    "あなたはタスク分解の専門家です。"
    "ユーザーの指示を具体的なサブタスクに分解してください。\n\n"
    "以下のJSON形式のみで回答してください（説明文は不要）:\n"
    '{"tasks": ["タスク1の説明", "タスク2の説明", ...]}\n\n'
    "ルール:\n"
    "- 各タスクは1ステップで実行可能な粒度にする\n"
    "- タスク数は最大10個まで\n"
    "- 日本語で記述する\n"
    "- JSONのみを返す（マークダウンのコードブロックも使わない）"
)


class Planner:
    """ユーザー指示をサブタスクに分解する.

    LLMを使ってユーザーの指示を段階的な実行計画に変換する。
    """

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    async def plan(self, instruction: str) -> list[SubTask]:
        """ユーザー指示からサブタスクリストを生成する.

        Args:
            instruction: ユーザーからの指示テキスト。

        Returns:
            サブタスクのリスト。LLM呼び出し失敗時は単一タスクを返す。
        """
        messages = [
            SystemMessage(content=_PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=instruction),
        ]

        try:
            response = await self._model.ainvoke(messages)
            content = response.content if isinstance(response.content, str) else ""
            parsed = json.loads(content)
            tasks = parsed.get("tasks", [])
            return [
                SubTask(description=task) for task in tasks if isinstance(task, str)
            ]
        except Exception:
            logger.warning(
                "Planner: LLM呼び出しに失敗。元の指示を単一タスクとして使用します。"
            )
            return [SubTask(description=instruction)]

    async def replan(
        self,
        instruction: str,
        failed_tasks: list[SubTask],
    ) -> list[SubTask]:
        """失敗したタスクを考慮してリプランする.

        Args:
            instruction: 元のユーザー指示。
            failed_tasks: 失敗したサブタスクのリスト。

        Returns:
            修正されたサブタスクのリスト。
        """
        failed_descriptions = "\n".join(
            f"- {t.description}: {t.result}" for t in failed_tasks
        )
        replan_instruction = (
            f"元の指示: {instruction}\n\n"
            f"以下のタスクが失敗しました:\n{failed_descriptions}\n\n"
            "失敗を考慮して、新しい実行計画を立ててください。"
        )
        return await self.plan(replan_instruction)
