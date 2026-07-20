"""Evaluate deterministic hybrid reranking on sanitized synthetic candidates."""

from __future__ import annotations

from dataclasses import dataclass

from backend.interfaces import RetrievalResult
from backend.rag.reranker import HybridReranker


@dataclass(frozen=True, slots=True)
class Case:
    query: str
    expected: str
    candidates: tuple[RetrievalResult, ...]


def candidate(conversation: str, title: str, content: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        content=content,
        score=score,
        source_kind="chunk",
        source_id=f"chunk-{conversation}",
        conversation_id=conversation,
        conversation_title=title,
        user_id="synthetic-user",
        source_message_ids=(f"message-{conversation}",),
    )


CASES = (
    Case(
        "Tell me about my artificial intelligence assignment?",
        "assignment",
        (
            candidate("drone", "Drone Project", "An AI model detects drones with OpenCV.", 0.64),
            candidate("assignment", "University Coursework", "The professor allowed AI for this assignment.", 0.56),
            candidate("hackathon", "OpenAI Hackathon", "We built an AI memory demo.", 0.61),
            candidate("job", "Job Application", "I described my AI candidate experience.", 0.60),
        ),
    ),
    Case(
        "What was my workout plan?",
        "workout",
        (
            candidate("travel", "Travel Plan", "The plan covered trains and hotels.", 0.60),
            candidate("workout", "Fitness Routine", "My workout plan used three exercise days.", 0.52),
        ),
    ),
    Case(
        "What did I try to cook?",
        "cooking",
        (
            candidate("project", "Weekend Project", "I tried a small software project.", 0.58),
            candidate("cooking", "Sourdough Baking", "I baked bread with starter and fermentation.", 0.50),
        ),
    ),
    Case(
        "What was I doing with my drone detector?",
        "drone",
        (
            candidate("ml", "Machine Learning", "A detector model was evaluated.", 0.62),
            candidate("drone", "Drone Detection", "The drone detector used a camera and CUDA.", 0.54),
        ),
    ),
    Case(
        "Tell me about the OpenAI hackathon",
        "hackathon",
        (
            candidate("job", "AI Job Application", "OpenAI was listed in a candidate paragraph.", 0.63),
            candidate("hackathon", "OpenAI Hackathon", "The OpenAI hackathon project built memory retrieval.", 0.55),
        ),
    ),
)


def main() -> None:
    configurations = (
        (1.00, 0.00, 0.00),
        (0.90, 0.07, 0.03),
        (0.85, 0.10, 0.05),
        (0.80, 0.12, 0.08),
        (0.75, 0.15, 0.10),
        (0.65, 0.20, 0.15),
    )
    print("Weight sweep (semantic/content/title):")
    for semantic, content, title in configurations:
        candidate_reranker = HybridReranker(
            semantic_weight=semantic, content_weight=content, title_weight=title
        )
        correct = sum(
            candidate_reranker.rerank(case.query, case.candidates, limit=1)[0].conversation_id
            == case.expected
            for case in CASES
        )
        print(f"  {semantic:.2f}/{content:.2f}/{title:.2f}: {correct}/{len(CASES)}")

    reranker = HybridReranker()
    print("Selected 0.75/0.15/0.10: highest semantic weight with 5/5 on this set.")
    for case in CASES:
        result = reranker.rerank(case.query, case.candidates, limit=1)[0]
        print(f'{"PASS" if result.conversation_id == case.expected else "FAIL"}: "{case.query}" -> {result.conversation_title}')


if __name__ == "__main__":
    main()
