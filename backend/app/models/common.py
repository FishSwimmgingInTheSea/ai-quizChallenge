"""通用类型定义。"""

from __future__ import annotations

from typing import Literal

QuestionType = Literal["single", "multiple", "judge"]
Difficulty = Literal["easy", "medium", "hard"]
DifficultyRequest = Literal["easy", "medium", "hard", "mixed"]
TaskStatus = Literal["pending", "generating", "done", "failed"]
