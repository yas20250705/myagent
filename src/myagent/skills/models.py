"""スキルデータモデル定義."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class SkillMetadata:
    """スキルのメタデータ（Progressive Disclosure: 起動時にロード）."""

    name: str
    description: str
    skill_dir: Path
    scope: Literal["project", "global"]
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)

    @property
    def skill_md_path(self) -> Path:
        """SKILL.md ファイルのパスを返す."""
        return self.skill_dir / "SKILL.md"


@dataclass
class Skill:
    """アクティベート済みスキル（メタデータ + ボディ）."""

    meta: SkillMetadata
    body: str  # SKILL.md のボディ（Markdownコンテンツ）
