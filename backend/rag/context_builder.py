"""Compact, ranked, attributed context construction."""

from collections.abc import Sequence

from backend.interfaces import RetrievalResult


class CompactContextBuilder:
    HEADER = "[Memora Context]\n"
    FOOTER = "\n[/Memora Context]"

    def build(
        self, query: str, results: Sequence[RetrievalResult], *, max_chars: int
    ) -> str:
        if max_chars <= 0 or not results:
            return ""
        sections = []
        for result in results:
            title = result.conversation_title or result.conversation_id or "Previous conversation"
            points = "\n".join(
                f"* {line.strip()}" for line in result.content.splitlines() if line.strip()
            )
            sections.append(
                f"Source: {title}\n\nUser previously discussed:\n\n{points}"
            )
        body = "\n\n".join(sections)
        full = f"{self.HEADER}{body}{self.FOOTER}"
        if len(full) <= max_chars:
            return full
        minimum = len(self.HEADER) + len(self.FOOTER)
        if max_chars < minimum:
            return full[:max_chars]
        available = max_chars - minimum
        return f"{self.HEADER}{body[:available].rstrip()}{self.FOOTER}"
