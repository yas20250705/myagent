"""プロンプト管理モジュール.

タスク種別に応じたプロンプトテンプレートの選択・結合を提供する。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

TaskType = Literal["general", "coding", "research", "refactoring"]

# デフォルトのプロンプトテンプレートディレクトリ
_DEFAULT_PROMPTS_DIR = Path(__file__).parent / "prompts"

# タスク種別とテンプレートファイルの対応
_TASK_TEMPLATES: dict[str, str] = {
    "coding": "coding.txt",
    "research": "research.txt",
    "refactoring": "refactoring.txt",
}


class PromptManager:
    """タスク種別に応じたプロンプトテンプレートを管理する.

    外部テキストファイルからテンプレートを読み込み、
    タスク種別に応じてベーステンプレートと追加テンプレートを結合する。
    """

    def __init__(self, prompts_dir: Path | None = None) -> None:
        """PromptManager を初期化する.

        Args:
            prompts_dir: テンプレートディレクトリ。Noneの場合はデフォルトを使用。
        """
        self._prompts_dir = prompts_dir or _DEFAULT_PROMPTS_DIR

    def _load_template(self, name: str) -> str:
        """テンプレートファイルを読み込む.

        Args:
            name: テンプレートファイル名。

        Returns:
            テンプレート内容。ファイルが見つからない場合は空文字列。
        """
        path = self._prompts_dir / name
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("プロンプトテンプレートが見つかりません: %s", path)
            return ""
        except OSError as e:
            logger.warning(
                "プロンプトテンプレートの読み込みに失敗: %s: %s", path, e
            )
            return ""

    def build_prompt(
        self,
        task_type: TaskType = "general",
        project_index: str | None = None,
    ) -> str:
        """タスク種別に応じたシステムプロンプトを構築する.

        ベーステンプレートに、タスク種別固有のテンプレートと
        プロジェクトインデックスを結合して返す。

        Args:
            task_type: タスク種別。
            project_index: プロジェクトファイルツリー文字列。

        Returns:
            構築されたシステムプロンプト。
        """
        base = self._load_template("base.txt")
        if not base:
            logger.warning("ベーステンプレートが空です。フォールバックプロンプトを使用します。")
            base = "あなたはAIアシスタントです。ユーザーの指示に従ってください。"

        parts = [base]

        # タスク種別固有のテンプレートを追加
        template_name = _TASK_TEMPLATES.get(task_type)
        if template_name:
            task_template = self._load_template(template_name)
            if task_template:
                parts.append(task_template)

        # プロジェクトインデックスを追加
        if project_index:
            parts.append(f"## プロジェクト構造\n\n{project_index}")

        return "\n\n".join(parts)
