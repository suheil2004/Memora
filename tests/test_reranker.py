import unittest

from backend.interfaces import RetrievalResult
from backend.rag.reranker import (
    HybridReranker, entity_dominant_course_code, extract_course_codes,
)


def result(
    conversation_id: str,
    title: str,
    content: str,
    score: float,
    *,
    chunk_id: str | None = None,
) -> RetrievalResult:
    source_id = chunk_id or f"chunk-{conversation_id}"
    return RetrievalResult(
        content=content,
        score=score,
        source_kind="chunk",
        source_id=source_id,
        conversation_id=conversation_id,
        conversation_title=title,
        user_id="synthetic-user",
        source_message_ids=(f"message-{source_id}",),
    )


class HybridRerankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reranker = HybridReranker()

    def test_ambiguous_topics_use_significant_terms_to_improve_precision(self) -> None:
        cases = (
            (
                "Tell me about my artificial intelligence assignment?",
                "assignment",
                (
                    result("drone", "Drone Project", "An AI model detects drones.", 0.64),
                    result("assignment", "University Coursework", "The professor allowed AI for this assignment.", 0.56),
                    result("hackathon", "OpenAI Hackathon", "We built an AI memory demo.", 0.61),
                ),
            ),
            (
                "What was my workout plan?",
                "workout",
                (
                    result("travel", "Travel Plan", "The plan covered hotels.", 0.60),
                    result("workout", "Fitness Routine", "My workout plan used three exercise days.", 0.52),
                ),
            ),
            (
                "What did I try to cook?",
                "cooking",
                (
                    result("project", "Weekend Project", "I tried a software project.", 0.58),
                    result("cooking", "Sourdough Baking", "I baked bread with starter.", 0.50),
                ),
            ),
            (
                "What was I doing with my drone detector?",
                "drone",
                (
                    result("ml", "Machine Learning", "A detector model was evaluated.", 0.62),
                    result("drone", "Drone Detection", "The drone detector used CUDA.", 0.54),
                ),
            ),
            (
                "Tell me about the OpenAI hackathon",
                "hackathon",
                (
                    result("job", "AI Job Application", "OpenAI appeared in a candidate paragraph.", 0.63),
                    result("hackathon", "OpenAI Hackathon", "The OpenAI hackathon built memory retrieval.", 0.55),
                ),
            ),
        )

        for query, expected, candidates in cases:
            with self.subTest(query=query):
                ranked = self.reranker.rerank(query, candidates, limit=1)
                self.assertEqual(ranked[0].conversation_id, expected)

    def test_conversation_diversity_keeps_only_the_strongest_reranked_chunk(self) -> None:
        weaker_duplicate = result(
            "assignment", "University Coursework", "A general AI discussion.", 0.62,
            chunk_id="assignment-general",
        )
        strongest = result(
            "assignment", "University Coursework",
            "The professor allowed AI for the assignment.", 0.58,
            chunk_id="assignment-specific",
        )
        distractor = result(
            "drone", "Drone Project", "An AI detector project.", 0.60,
        )

        ranked = self.reranker.rerank(
            "artificial intelligence assignment", (weaker_duplicate, strongest, distractor), limit=3
        )

        self.assertEqual([item.conversation_id for item in ranked], ["assignment", "drone"])
        self.assertEqual(ranked[0].source_id, "assignment-specific")
        self.assertEqual(ranked[0].source_message_ids, ("message-assignment-specific",))

    def test_empty_candidates_preserve_no_match_behavior(self) -> None:
        self.assertEqual(self.reranker.rerank("unrelated query", (), limit=5), ())

    def test_course_code_variants_normalize_identically(self) -> None:
        expected = frozenset({"COMP 472"})
        for value in ("COMP472", "COMP 472", "COMP-472", "comp472"):
            with self.subTest(value=value):
                self.assertEqual(extract_course_codes(value), expected)

    def test_only_broad_exact_course_queries_activate_entity_first_mode(self) -> None:
        for query in (
            "Tell me about COMP 472", "What was COMP472?", "Remind me about COMP-472",
        ):
            with self.subTest(query=query):
                self.assertEqual(entity_dominant_course_code(query), "COMP 472")
        for query in (
            "What assignments did I work on for COMP 472?",
            "What practice exam did I discuss for COMP 472?",
            "Tell me about my artificial intelligence course",
            "Tell me about 472", "What happened in 2025?", "Tell me about project 290",
        ):
            with self.subTest(query=query):
                self.assertIsNone(entity_dominant_course_code(query))

    def test_exact_course_entity_outranks_and_mismatch_penalizes(self) -> None:
        candidates = (
            result(
                "engr", "ENGR 290 Project",
                "An engineering assignment used a Firebase Android application.", 0.78,
            ),
            result(
                "comp", "COMP-472 Artificial Intelligence",
                "Course assignments and practice exams were discussed.", 0.57,
            ),
            result(
                "firebase", "Android Firebase Application",
                "Mobile application coursework and project implementation.", 0.73,
            ),
        )
        ranked = self.reranker.rank_candidates("What assignments did I do for COMP 472?", candidates)
        self.assertEqual(ranked[0].result.conversation_id, "comp")
        self.assertTrue(ranked[0].entity_match)
        engr = next(item for item in ranked if item.result.conversation_id == "engr")
        self.assertTrue(engr.entity_mismatch)
        self.assertLess(engr.hybrid_score, ranked[0].hybrid_score)

        practice_ranked = self.reranker.rank_candidates(
            "What practice exam did I discuss for COMP 472?",
            (
                result("engr-exam", "ENGR 290 Exam", "ENGR 290 practice exam.", 0.79),
                result("comp-exam", "COMP 472 Practice Exam", "COMP472 practice exam notes.", 0.58),
            ),
        )
        self.assertEqual(practice_ranked[0].result.conversation_id, "comp-exam")

    def test_academic_intent_disambiguates_ai_course_from_ai_projects(self) -> None:
        candidates = (
            result("report", "Generative AI Ethics Report", "A report studied generative AI use.", 0.66),
            result("course", "COMP 472 Artificial Intelligence", "Course assignments, professor notes, and practice exams.", 0.61),
            result("hackathon", "OpenAI Hackathon", "An AI project built a memory product.", 0.64),
            result("drone", "Drone AI Project", "Artificial intelligence detected drones.", 0.63),
        )
        ranked = self.reranker.rerank(
            "Tell me about my artificial intelligence course", candidates, limit=1
        )
        self.assertEqual(ranked[0].conversation_id, "course")


if __name__ == "__main__":
    unittest.main()
