"""LLM-as-judge evaluation for generation quality.

A judge model scores answers on faithfulness (claims supported by the
retrieved context). Judge scores are noisy — treat them as regression
signals across versions, not absolute truth.
"""
import json
from dataclasses import dataclass

from ai.llm.client import get_llm_client
from ai.llm.prompts import LLM_JUDGE_FAITHFULNESS
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class JudgeScore:
    score: float  # 1-5
    reasoning: str


async def judge_faithfulness(question: str, context: str, answer: str) -> JudgeScore:
    try:
        result = await get_llm_client().chat(
            [
                {
                    "role": "user",
                    "content": LLM_JUDGE_FAITHFULNESS.render(
                        question=question, context=context[:8000], answer=answer
                    ),
                }
            ],
            temperature=0.0,
            max_tokens=200,
            response_format={"type": "json_object"},
            operation="judge",
        )
        data = json.loads(result.content)
        return JudgeScore(score=float(data["score"]), reasoning=data.get("reasoning", ""))
    except Exception as e:
        logger.warning("judge_failed", error=str(e))
        return JudgeScore(score=0.0, reasoning=f"judge error: {e}")
