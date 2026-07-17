"""Evaluate Memora retrieval rankings over paraphrased queries."""

from __future__ import annotations

import argparse
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.json_importer import JsonConversationImporter
from backend.models import User
from backend.rag.pipeline import index_conversation
from backend.rag.provider import create_embedding_service
from backend.rag.retriever import SemanticMemoryRetriever


SAMPLE_FILES = (
    "drone_detection.json",
    "sourdough.json",
    "university_coursework.json",
    "travel_planning.json",
    "event_planning.json",
)


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    expected: str
    query: str


CASES = (
    EvaluationCase("Drone Detection Project", "Why is my vision system responding too slowly?"),
    EvaluationCase("Drone Detection Project", "Could moving more processing onto the Pi improve my setup?"),
    EvaluationCase("Drone Detection Project", "Where is the neural network actually running in my current hardware architecture?"),
    EvaluationCase("Drone Detection Project", "What computer handles detection in the system I was working on?"),
    EvaluationCase("Drone Detection Project", "Remind me how the camera and inference workload are divided."),
    EvaluationCase("Sourdough Baking", "How did I want the outside and holes of my homemade loaf to turn out?"),
    EvaluationCase("Sourdough Baking", "What kind of culture do I maintain for weekend bread making?"),
    EvaluationCase("University Coursework", "When is the assignment about concurrent data operations due?"),
    EvaluationCase("University Coursework", "What experiment did we suggest for my class report on faster lookups?"),
    EvaluationCase("Travel Planning", "Which two Japanese cities am I visiting in early fall?"),
    EvaluationCase("Travel Planning", "What dietary preference should shape restaurant choices on my vacation?"),
    EvaluationCase("Travel Planning", "Which nearby destination did I want to visit for one day?"),
    EvaluationCase("Event Planning", "What equipment does the gathering space need for the speakers?"),
    EvaluationCase("Event Planning", "Who is checking people in at the neighborhood gathering?"),
    EvaluationCase("Event Planning", "Roughly how many attendees are we preparing to host?"),
)


def evaluate(provider: str) -> tuple[int, int, int]:
    embeddings = create_embedding_service(provider)
    importer = JsonConversationImporter()
    chunker = ConversationChunker(max_tokens=120, overlap_tokens=20)
    user = User(f"evaluation-{provider}")
    root = Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory() as directory:
        store = SQLiteVectorStore(Path(directory) / "evaluation.sqlite3")
        for filename in SAMPLE_FILES:
            imported = importer.import_file(root / "samples" / filename, user_id=user.id)[0]
            index_conversation(
                imported, user=user, chunker=chunker, embeddings=embeddings, store=store
            )

        retriever = SemanticMemoryRetriever(embeddings, store)
        top1 = 0
        top3 = 0
        print(f"\n=== {provider.upper()} ({embeddings.model_name}) ===")
        for case in CASES:
            results = retriever.retrieve(case.query, user_id=user.id, limit=3, min_similarity=-1.0)
            titles = [result.conversation_title for result in results]
            passed = bool(titles) and titles[0] == case.expected
            top1 += int(passed)
            top3 += int(case.expected in titles)
            print(f'\nQuery: "{case.query}"')
            print(f"Expected: {case.expected}")
            for rank, result in enumerate(results, start=1):
                print(f"  {rank}. {(result.conversation_title or 'Untitled'):<28} {result.score:.4f}")
            print("PASS" if passed else "FAIL")

    total = len(CASES)
    print(f"\nTop-1 Accuracy: {top1}/{total} ({top1 / total:.1%})")
    print(f"Top-3 Accuracy: {top3}/{total} ({top3 / total:.1%})")
    return top1, top3, total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=("local", "openai", "both"),
        default="openai",
        help="Embedding provider to evaluate (default: openai)",
    )
    args = parser.parse_args()
    providers = ("local", "openai") if args.provider == "both" else (args.provider,)
    if "openai" in providers and not os.environ.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY must be set for OpenAI evaluation")
    summaries = [evaluate(provider) for provider in providers]
    if len(summaries) == 2:
        print("\n=== RANKING ACCURACY COMPARISON ===")
        for provider, (top1, top3, total) in zip(providers, summaries):
            print(f"{provider:<8} Top-1 {top1}/{total}; Top-3 {top3}/{total}")


if __name__ == "__main__":
    main()
