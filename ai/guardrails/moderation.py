"""Output moderation: final check before an answer leaves the system.

Verifies the model didn't leak the system prompt and strips any leftover
internal markers. Kept simple and deterministic — output moderation must be
fast and must not fail.
"""
import re
from dataclasses import dataclass

LEAK_MARKERS = [
    re.compile(r"you are cortex, an enterprise knowledge (assistant|agent)", re.IGNORECASE),
    re.compile(r"## context\n", re.IGNORECASE),
    re.compile(r"system prompt\s{0,8}:", re.IGNORECASE),
]
STREAM_LOOKAHEAD = max(len(marker.pattern) + 8 for marker in LEAK_MARKERS)


@dataclass
class ModerationResult:
    text: str
    flagged: bool
    reason: str = ""


def moderate_output(text: str) -> ModerationResult:
    for marker in LEAK_MARKERS:
        if marker.search(text):
            return ModerationResult(
                text="I can't share internal system details. How else can I help?",
                flagged=True,
                reason=f"system_prompt_leak: {marker.pattern}",
            )
    return ModerationResult(text=text, flagged=False)


class StreamingOutputModerator:
    """Hold back enough text to detect configured leak markers before release."""

    def __init__(self) -> None:
        self._released = ""
        self._pending = ""
        self._replacement: str | None = None

    @property
    def flagged(self) -> bool:
        return self._replacement is not None

    def feed(self, text: str) -> str:
        if self.flagged:
            return ""
        self._pending += text
        result = moderate_output(self._released + self._pending)
        if result.flagged:
            self._replacement = result.text
            self._pending = ""
            return ""

        safe_length = max(0, len(self._pending) - STREAM_LOOKAHEAD)
        safe_text, self._pending = self._pending[:safe_length], self._pending[safe_length:]
        self._released += safe_text
        return safe_text

    def finish(self) -> ModerationResult:
        if self.flagged:
            return ModerationResult(self._replacement or "", flagged=True)
        result = moderate_output(self._released + self._pending)
        if result.flagged:
            self._replacement = result.text
            self._pending = ""
            return result
        remainder, self._pending = self._pending, ""
        return ModerationResult(remainder, flagged=False)
