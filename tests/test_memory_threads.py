import unittest
from datetime import datetime, timezone

from backend.interfaces import RetrievalResult
from backend.rag.memory_threads import MemoryThreadGrouper
from backend.rag.reranker import HybridReranker


def evidence(
    conversation_id: str,
    title: str,
    content: str,
    score: float,
    *,
    created_at: datetime | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        content=content,
        score=score,
        source_kind="chunk",
        source_id=f"chunk-{conversation_id}",
        conversation_id=conversation_id,
        conversation_title=title,
        user_id="synthetic-user",
        source_message_ids=(f"message-{conversation_id}",),
        source_created_at=created_at,
    )


class MemoryThreadGroupingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reranker = HybridReranker()
        self.grouper = MemoryThreadGrouper()

    def _group(self, query: str, candidates: tuple[RetrievalResult, ...]):
        ranked = self.reranker.rank_candidates(query, candidates)
        return self.grouper.group(query, ranked, limit=5)

    def test_workout_subjects_and_materially_different_plans_remain_separate(self) -> None:
        eligible_workout_evidence = (
            evidence(
                "girlfriend-pilates", "Pilates Plan",
                "I created a Pilates workout plan for my girlfriend focused on mobility.", 0.72,
            ),
            evidence(
                "user-cardio", "Running Progression",
                "I planned my running and cardio progression with gradually longer sessions.", 0.70,
            ),
            evidence(
                "user-fat-loss", "Fat Loss Routine",
                "My fat-loss workout routine combined strength circuits and calorie goals.", 0.68,
            ),
            # Puppy-care evidence is intentionally absent: the semantic threshold gate
            # excludes it before candidates reach thread grouping.
        )

        grouped = self._group("Tell me about my workout plan", eligible_workout_evidence)
        threads = [thread for thread, _ in grouped]

        self.assertEqual(len(threads), 3)
        self.assertEqual({thread.subject for thread in threads}, {"girlfriend", "user"})
        self.assertEqual(
            {thread.source_conversation_ids[0] for thread in threads},
            {"girlfriend-pilates", "user-cardio", "user-fat-loss"},
        )

    def test_distinct_drone_projects_do_not_merge(self) -> None:
        grouped = self._group(
            "Tell me about my drone projects",
            (
                evidence(
                    "detector", "Drone Detection Project",
                    "I built a drone detector using camera inference and CUDA.", 0.75,
                ),
                evidence(
                    "fire-drone", "Fire Extinguishing Drone",
                    "I designed a fire-extinguishing drone with a water tank and pump.", 0.73,
                ),
            ),
        )

        self.assertEqual(len(grouped), 2)
        self.assertEqual(
            {thread.source_conversation_ids for thread, _ in grouped},
            {("detector",), ("fire-drone",)},
        )

    def test_one_conversation_can_hold_distinct_subject_threads(self) -> None:
        first = evidence(
            "shared-chat", "Workout Discussion",
            "I made a Pilates mobility workout for my girlfriend.", 0.72,
        )
        second = RetrievalResult(
            content="My running cardio progression used longer intervals.",
            score=0.70,
            source_kind="chunk",
            source_id="chunk-shared-chat-cardio",
            conversation_id="shared-chat",
            conversation_title="Workout Discussion",
            user_id="synthetic-user",
            source_message_ids=("message-shared-chat-cardio",),
        )
        grouped = self._group("Tell me about my workout plan", (first, second))
        self.assertEqual(len(grouped), 2)
        self.assertEqual({thread.subject for thread, _ in grouped}, {"girlfriend", "user"})

    def test_strong_same_project_continuity_can_merge_conversations(self) -> None:
        first_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        second_time = datetime(2026, 1, 8, tzinfo=timezone.utc)
        grouped = self._group(
            "How did my drone detector camera inference work?",
            (
                evidence(
                    "detector-setup", "Drone Detection Project",
                    "I built the drone detector camera pipeline and CUDA inference.", 0.76,
                    created_at=first_time,
                ),
                evidence(
                    "detector-followup", "Drone Detection Follow-up",
                    "I continued my drone detection camera and inference pipeline work.", 0.74,
                    created_at=second_time,
                ),
            ),
        )

        self.assertEqual(len(grouped), 1)
        thread, representative = grouped[0]
        self.assertEqual(
            set(thread.source_conversation_ids), {"detector-setup", "detector-followup"}
        )
        self.assertEqual(
            set(thread.source_chunk_ids), {"chunk-detector-setup", "chunk-detector-followup"}
        )
        self.assertEqual(
            set(thread.source_message_ids),
            {"message-detector-setup", "message-detector-followup"},
        )
        self.assertEqual(thread.source_timestamps, (first_time, second_time))
        self.assertIn(
            representative.conversation_id, {"detector-setup", "detector-followup"}
        )
        self.assertEqual(
            thread.thread_id,
            self._group(
                "How did my drone detector camera inference work?",
                tuple(reversed((
                    evidence(
                        "detector-setup", "Drone Detection Project",
                        "I built the drone detector camera pipeline and CUDA inference.", 0.76,
                        created_at=first_time,
                    ),
                    evidence(
                        "detector-followup", "Drone Detection Follow-up",
                        "I continued my drone detection camera and inference pipeline work.", 0.74,
                        created_at=second_time,
                    ),
                ))),
            )[0][0].thread_id,
        )

    def test_explicit_version_markers_prevent_cross_conversation_merge(self) -> None:
        grouped = self._group(
            "What was my running plan?",
            (
                evidence(
                    "old-plan", "Old Running Plan",
                    "My old running cardio progression used short intervals.", 0.70,
                ),
                evidence(
                    "updated-plan", "Updated Running Plan",
                    "My updated running cardio progression used longer intervals.", 0.69,
                ),
            ),
        )
        self.assertEqual(len(grouped), 2)

    def test_same_course_and_task_can_merge_across_conversations(self) -> None:
        grouped = self._group(
            "What assignments did I work on for COMP 472?",
            (
                evidence("assignment-one", "COMP 472 Assignment 1", "COMP472 course assignment about search algorithms.", 0.72),
                evidence("assignment-two", "COMP-472 Assignment Follow-up", "COMP 472 assignment work continued with algorithm evaluation.", 0.70),
            ),
        )
        self.assertEqual(len(grouped), 1)
        self.assertEqual(
            set(grouped[0][0].source_conversation_ids),
            {"assignment-one", "assignment-two"},
        )

    def test_course_code_is_boundary_and_distinct_tasks_remain_subthreads(self) -> None:
        grouped = self._group(
            "Tell me about COMP 472 coursework",
            (
                evidence("comp-assignment", "COMP 472 Assignment", "COMP 472 assignment work used search algorithms.", 0.74),
                evidence("comp-exam", "COMP 472 Practice Exam", "COMP472 practice exam preparation covered heuristics.", 0.72),
                evidence("engr-assignment", "ENGR 290 Assignment", "ENGR 290 assignment involved an Android Firebase project.", 0.76),
            ),
        )
        self.assertEqual(len(grouped), 3)
        self.assertEqual(
            {thread.source_conversation_ids for thread, _ in grouped},
            {("comp-assignment",), ("comp-exam",), ("engr-assignment",)},
        )


if __name__ == "__main__":
    unittest.main()
