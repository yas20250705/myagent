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

_PLANNER_DEPENDENCY_PROMPT = (
    "あなたはタスク分解と依存関係分析の専門家です。"
    "ユーザーの指示を具体的なサブタスクに分解し、"
    "各タスク間の依存関係と対象ファイルを特定してください。\n\n"
    "以下のJSON形式のみで回答してください（説明文は不要）:\n"
    '{"tasks": [\n'
    '  {"id": "t1", "description": "タスクの説明", '
    '"depends_on": [], "target_files": ["src/foo.py"]},\n'
    '  {"id": "t2", "description": "タスクの説明", '
    '"depends_on": ["t1"], "target_files": ["src/bar.py"]}\n'
    "]}\n\n"
    "ルール:\n"
    "- 各タスクは1ステップで実行可能な粒度にする\n"
    "- タスク数は最大10個まで\n"
    "- idは t1, t2, ... の連番\n"
    "- depends_on には、このタスクの前に完了すべきタスクのidを指定\n"
    "- 独立して実行可能なタスクの depends_on は空リスト []\n"
    "- target_files には、このタスクが読み書きする可能性のあるファイルパスを指定\n"
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

    async def plan_with_dependencies(self, instruction: str) -> list[SubTask]:
        """ユーザー指示からサブタスクリストを依存関係付きで生成する.

        LLMに依存関係と対象ファイルを含むJSON形式で出力させる。
        パース失敗時は全タスクを連鎖依存（逐次実行）として返す。

        Args:
            instruction: ユーザーからの指示テキスト。

        Returns:
            依存関係付きサブタスクのリスト。
        """
        messages = [
            SystemMessage(content=_PLANNER_DEPENDENCY_PROMPT),
            HumanMessage(content=instruction),
        ]

        try:
            response = await self._model.ainvoke(messages)
            content = response.content if isinstance(response.content, str) else ""
            parsed = json.loads(content)
            tasks_data = parsed.get("tasks", [])

            subtasks: list[SubTask] = []
            for item in tasks_data:
                if not isinstance(item, dict):
                    continue
                description = item.get("description", "")
                if not description:
                    continue
                depends_on_raw = item.get("depends_on", [])
                depends_on = [d for d in depends_on_raw if isinstance(d, str)]
                target_files_raw = item.get("target_files", [])
                target_files = [f for f in target_files_raw if isinstance(f, str)]
                subtasks.append(
                    SubTask(
                        description=description,
                        task_id=item.get("id", ""),
                        depends_on=depends_on,
                        target_files=target_files,
                    )
                )

            if subtasks:
                return subtasks

        except Exception:
            logger.warning(
                "Planner: 依存関係分析に失敗。逐次実行としてフォールバックします。"
            )

        # フォールバック: 通常のplanを呼び、連鎖依存にする
        simple_tasks = await self.plan(instruction)
        for i, task in enumerate(simple_tasks):
            task.task_id = f"t{i + 1}"
            if i > 0:
                task.depends_on = [f"t{i}"]
        return simple_tasks

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
