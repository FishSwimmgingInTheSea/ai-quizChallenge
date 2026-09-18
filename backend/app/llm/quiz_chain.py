"""出题链：封装单题生成与题库元信息生成。

对外暴露 QuizGenerator 协议，服务层依赖协议而非具体实现，便于测试注入 mock。
"""

from __future__ import annotations

from typing import Protocol

from app.llm.langchain_factory import get_quiz_model, with_structured_output
from app.llm.output_schemas import QuestionDraft, QuizMetaDraft
from app.models.common import Difficulty, QuestionType
from app.prompts.quiz_prompt import quiz_meta_prompt, quiz_question_prompt


class QuizGenerator(Protocol):
    """出题生成器协议。"""

    async def generate_meta(
        self, user_input: str, question_count: int, difficulty: str
    ) -> QuizMetaDraft: ...

    async def generate_question(
        self,
        user_input: str,
        question_type: QuestionType,
        difficulty: Difficulty,
        index: int,
        existing_stems: list[str],
    ) -> QuestionDraft: ...


class LangChainQuizGenerator:
    """基于 LangChain + DeepSeek 的真实出题生成器。"""

    def __init__(self) -> None:
        model = get_quiz_model()
        self._meta_chain = quiz_meta_prompt | with_structured_output(model, QuizMetaDraft)
        self._question_chain = quiz_question_prompt | with_structured_output(
            model, QuestionDraft
        )

    async def generate_meta(
        self, user_input: str, question_count: int, difficulty: str
    ) -> QuizMetaDraft:
        return await self._meta_chain.ainvoke({"user_input": user_input})

    async def generate_question(
        self,
        user_input: str,
        question_type: QuestionType,
        difficulty: Difficulty,
        index: int,
        existing_stems: list[str],
    ) -> QuestionDraft:
        stems_text = (
            "\n".join(f"- {s}" for s in existing_stems) if existing_stems else "（暂无）"
        )
        return await self._question_chain.ainvoke(
            {
                "user_input": user_input,
                "question_type": question_type,
                "difficulty": difficulty,
                "index": index,
                "existing_stems": stems_text,
            }
        )
