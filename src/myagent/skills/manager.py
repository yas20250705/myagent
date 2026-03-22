"""スキル管理のコアクラス."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal

from myagent.skills.loader import parse_skill_body, parse_skill_md
from myagent.skills.models import Skill, SkillMetadata

logger = logging.getLogger(__name__)

_DEFAULT_GLOBAL_SKILLS_DIR = Path.home() / ".myagent" / "skills"


class SkillManager:
    """スキルの検出・ロード・アクティベーションを管理する.

    Progressive Disclosure: 起動時はメタデータのみをロード。
    ボディは activate() 時にオンデマンドで読み込む。

    スコープ優先度: project > global
    同名スキルはプロジェクトローカルが優先する。
    """

    def __init__(
        self,
        project_skills_dir: Path | None = None,
        global_skills_dir: Path | None = None,
        extra_skill_dirs: list[Path] | None = None,
    ) -> None:
        """初期化.

        Args:
            project_skills_dir: プロジェクトローカルスキルのディレクトリ。
            global_skills_dir: グローバルスキルのディレクトリ。
                               None の場合は ~/.myagent/skills を使用。
            extra_skill_dirs: プラグイン等から追加されるスキルディレクトリリスト。
        """
        self._project_dir = project_skills_dir
        self._global_dir = global_skills_dir or _DEFAULT_GLOBAL_SKILLS_DIR
        self._extra_dirs = extra_skill_dirs or []
        # name -> SkillMetadata（プロジェクトローカルが優先）
        self._skills: dict[str, SkillMetadata] = {}
        self._loaded = False

    def load_all(self) -> list[SkillMetadata]:
        """全スキルのメタデータを検出・ロードする.

        プロジェクトローカル → グローバルの順に検索。
        同名スキルはプロジェクトローカルが優先。

        Returns:
            ロード済みスキルのメタデータリスト。
        """
        self._skills = {}

        # グローバルスキルを先にロード（後でプロジェクトローカルで上書き）
        if self._global_dir and self._global_dir.is_dir():
            self._load_from_dir(self._global_dir, "global")

        # プラグイン提供スキルをロード（グローバルスコープ扱い）
        for extra_dir in self._extra_dirs:
            if extra_dir.is_dir():
                self._load_from_dir(extra_dir, "global")

        # プロジェクトローカルスキルをロード（優先度高い）
        if self._project_dir and self._project_dir.is_dir():
            self._load_from_dir(self._project_dir, "project")

        self._loaded = True
        logger.debug("スキルをロードしました: %d 個", len(self._skills))
        return list(self._skills.values())

    def get_all_metadata(self) -> list[SkillMetadata]:
        """ロード済みスキルのメタデータリストを返す."""
        if not self._loaded:
            self.load_all()
        return list(self._skills.values())

    def get_metadata(self, name: str) -> SkillMetadata | None:
        """名前からスキルのメタデータを取得する.

        Args:
            name: スキル名。

        Returns:
            見つかった場合は SkillMetadata、見つからない場合は None。
        """
        if not self._loaded:
            self.load_all()
        return self._skills.get(name)

    def activate(self, name: str) -> Skill | None:
        """スキルをアクティベートし、ボディを含む Skill を返す.

        SKILL.md ボディをオンデマンドで読み込む（Progressive Disclosure）。

        Args:
            name: アクティベートするスキル名。

        Returns:
            アクティベートされた Skill。見つからない場合は None。
        """
        meta = self.get_metadata(name)
        if meta is None:
            return None

        body = parse_skill_body(meta.skill_md_path)
        return Skill(meta=meta, body=body)

    def find_matching(self, instruction: str) -> list[SkillMetadata]:
        """ユーザーの指示文とスキルの description をマッチングする.

        description の単語が instruction に含まれるスキルを返す。
        単純なキーワードマッチングを使用。

        Args:
            instruction: ユーザーの指示文。

        Returns:
            マッチしたスキルのメタデータリスト（スコアの高い順）。
        """
        if not self._loaded:
            self.load_all()

        instruction_lower = instruction.lower()
        matches: list[tuple[int, SkillMetadata]] = []

        for meta in self._skills.values():
            score = _match_score(instruction_lower, meta.description.lower())
            if score > 0:
                matches.append((score, meta))

        matches.sort(key=lambda x: x[0], reverse=True)
        return [meta for _, meta in matches]

    # -----------------------------------------------------------------------
    # 内部ヘルパー
    # -----------------------------------------------------------------------

    def _load_from_dir(
        self,
        skills_dir: Path,
        scope: Literal["project", "global"],
    ) -> None:
        """スキルディレクトリ内の各スキルをロードする."""
        for entry in sorted(skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.exists():
                continue
            meta = parse_skill_md(skill_md, scope)
            if meta is not None:
                self._skills[meta.name] = meta


def _match_score(instruction_lower: str, description_lower: str) -> int:
    """指示文とdescriptionのマッチングスコアを計算する.

    スペース区切りの単語マッチングを基本とするが、
    日本語のように空白区切りがない言語への対応として
    description の前半部分が instruction に含まれる場合にも加点する。
    """
    score = 0

    # スペース区切りの各単語マッチング（英語向け）
    # \b を使った単語境界マッチング（"or"/"to" が "skill-creator" の部分文字列にマッチしないようにする）
    words = [w for w in description_lower.split() if len(w) >= 2]
    score += sum(
        1 for word in words if re.search(r"\b" + re.escape(word) + r"\b", instruction_lower)
    )

    # description の先頭 N 文字の部分一致（日本語向け）
    partial_len = 6
    if len(description_lower) >= partial_len:
        prefix = description_lower[:partial_len]
        if prefix in instruction_lower:
            score += 2

    return score
