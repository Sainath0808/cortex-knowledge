"""Prompt injection defense: fast heuristics + optional LLM classifier.

Layered defense:
1. Cheap regex heuristics catch obvious attacks with zero latency.
2. An LLM classifier (JSON output) catches subtler attempts.
3. The system prompts instruct the model to treat retrieved text as data.
No single layer is sufficient; together they raise the attack cost.
"""
import json
import re
from dataclasses import dataclass

from app.core.logging import get_logger

from ai.llm.prompts import INJECTION_CLASSIFIER

logger = get_logger(__name__)

HEURISTIC_PATTERNS = [
    r"ignore\s+(?:(?:all|any|the)\s+)?(?:(?:previous|above|prior)\s+)?"
    r"(?:instructions|prompts|rules)",
    r"disregard (the|your|all) (system|previous|above)",
    r"you are now (?!answering)",
    r"reveal (your|the) (system prompt|instructions|rules)",
    r"repeat (your|the) (system prompt|instructions)",
    r"\bdo anything now\b|\bDAN mode\b",
    r"pretend (you are|to be) (?!a helpful)",
    r"</?(system|assistant)>",
    r"\bBEGIN (SYSTEM|ADMIN) (PROMPT|OVERRIDE)\b",
]

_compiled = [re.compile(p, re.IGNORECASE) for p in HEURISTIC_PATTERNS]


@dataclass
class InjectionVerdict:
    blocked: bool
    reason: str
    layer: str  # heuristic | classifier | none


def heuristic_check(text: str) -> InjectionVerdict:
    for pattern in _compiled:
        if pattern.search(text):
            return InjectionVerdict(True, f"Matched pattern: {pattern.pattern}", "heuristic")
    return InjectionVerdict(False, "", "none")


async def classify_injection(text: str) -> InjectionVerdict:
    """LLM-based classification. Fails open with a warning (availability > strictness
    here because heuristics already ran; flip to fail-closed for high-risk deployments)."""
    from ai.llm.client import get_llm_client

    try:
        result = await get_llm_client().chat(
            [{"role": "user", "content": INJECTION_CLASSIFIER.render(text=text[:4000])}],
            temperature=0.0,
            max_tokens=100,
            response_format={"type": "json_object"},
            operation="injection_check",
        )
        data = json.loads(result.content)
        if data.get("injection"):
            return InjectionVerdict(True, data.get("reason", "classifier"), "classifier")
    except Exception as e:
        logger.warning("injection_classifier_failed", error=str(e))
    return InjectionVerdict(False, "", "none")


async def check_input(text: str, *, use_classifier: bool = True) -> InjectionVerdict:
    verdict = heuristic_check(text)
    if verdict.blocked:
        logger.warning("injection_blocked", layer="heuristic", reason=verdict.reason)
        return verdict
    if use_classifier:
        verdict = await classify_injection(text)
        if verdict.blocked:
            logger.warning("injection_blocked", layer="classifier", reason=verdict.reason)
    return verdict
