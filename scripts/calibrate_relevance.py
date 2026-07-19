"""Print raw retrieval scores from an existing database without modifying it."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from backend.database.sqlite_store import SQLiteVectorStore
from backend.rag.provider import create_embedding_service
from backend.rag.retriever import SemanticMemoryRetriever


@dataclass(frozen=True, slots=True)
class PositiveCase:
    expected: str
    query: str


POSITIVE_CASES = (
    PositiveCase("Drone Detection Project", "How was the camera feed being processed in my drone detection setup?"),
    PositiveCase("Drone Detection Project", "What computer was doing the inference for my drone project?"),
    PositiveCase("Drone Detection Project", "Where was I running my model again?"),
    PositiveCase("Drone Detection Project", "What device streamed the camera feed?"),
    PositiveCase("Drone Detection Project", "How did my drone tracking setup work?"),
    PositiveCase("Sourdough Baking", "What was I trying to bake?"),
    PositiveCase("Sourdough Baking", "What did I discuss about sourdough?"),
    PositiveCase("Sourdough Baking", "What was I doing with starter and fermentation?"),
    PositiveCase("University Coursework", "What experiment did we suggest for my class report on faster lookups?"),
    PositiveCase("University Coursework", "When was my database course report due?"),
    PositiveCase("Travel Planning", "Which two Japanese cities was I planning to visit?"),
    PositiveCase("Travel Planning", "What food preference mattered for my Japan trip?"),
    PositiveCase("Event Planning", "What equipment did the meetup venue need?"),
    PositiveCase("Event Planning", "How many guests was the community event expecting?"),
)

NEGATIVE_QUERIES = (
    "What is my workout plan?",
    "Where did I leave my keys?",
    "What medicine did I take yesterday?",
    "Who is my favorite singer?",
    "What video game was I playing?",
)

AMBIGUOUS_QUERIES = (
    "What did I try to cook?",
    "What was I working on?",
    "What was my plan?",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=_default_database())
    parser.add_argument("--provider", choices=("local", "openai"))
    parser.add_argument("--user-id", default=os.environ.get("MEMORA_USER_ID", "demo-user"))
    args = parser.parse_args()

    if not args.database.is_file():
        parser.error(f"database does not exist: {args.database}")
    embeddings = create_embedding_service(args.provider)
    store = SQLiteVectorStore(args.database, read_only=True)
    retriever = SemanticMemoryRetriever(embeddings, store)
    positive_scores: list[float] = []
    negative_scores: list[float] = []
    ambiguous_scores: list[float] = []
    missing_titles: set[str] = set()

    print(f"Database: {args.database.resolve()}")
    print(f"User: {args.user_id}")
    print(f"Embedding space: {embeddings.provider_name}/{embeddings.model_name}")
    print("Mode: read-only; raw scores use min_similarity=-1.0\n")

    print("=== POSITIVE ===")
    for case in POSITIVE_CASES:
        results = _raw_results(retriever, case.query, args.user_id)
        _print_results(case.query, results)
        expected = next(
            (result for result in results if result.conversation_title == case.expected), None
        )
        if expected is None:
            missing_titles.add(case.expected)
            print(f"Expected source unavailable: {case.expected}\n")
        else:
            positive_scores.append(expected.score)
            rank = results.index(expected) + 1
            print(f"Expected source: rank {rank}, raw score {expected.score:.6f}\n")

    print("=== NEGATIVE ===")
    for query in NEGATIVE_QUERIES:
        results = _raw_results(retriever, query, args.user_id)
        _print_results(query, results)
        if results:
            negative_scores.append(results[0].score)
        print()

    print("=== AMBIGUOUS ===")
    for query in AMBIGUOUS_QUERIES:
        results = _raw_results(retriever, query, args.user_id)
        _print_results(query, results)
        if results:
            ambiguous_scores.append(results[0].score)
        print()

    _print_summary(positive_scores, negative_scores, ambiguous_scores, missing_titles)


def _raw_results(retriever: SemanticMemoryRetriever, query: str, user_id: str):
    return retriever.retrieve(query, user_id=user_id, limit=10_000, min_similarity=-1.0)


def _print_results(query: str, results) -> None:
    print(f'Query: "{query}"')
    if not results:
        print("  No stored chunks for this user")
        return
    for rank, result in enumerate(results[:3], start=1):
        print(f"  Top {rank}: {result.conversation_title or 'Untitled'} — {result.score:.6f}")


def _print_summary(
    positives: list[float],
    negatives: list[float],
    ambiguous: list[float],
    missing_titles: set[str],
) -> None:
    print("=== CALIBRATION SUMMARY ===")
    if missing_titles:
        print("Missing expected sources: " + ", ".join(sorted(missing_titles)))
    if positives:
        print(f"Lowest measured positive: {min(positives):.6f}")
    if negatives:
        print(f"Highest measured negative: {max(negatives):.6f}")
    if ambiguous:
        print(f"Ambiguous top-score range: {min(ambiguous):.6f} to {max(ambiguous):.6f}")
    if missing_titles:
        print("No threshold recommendation: import the complete synthetic corpus first.")
    elif positives and negatives and max(negatives) < min(positives):
        midpoint = (max(negatives) + min(positives)) / 2
        print(f"Clean separation observed; midpoint candidate: {midpoint:.6f}")
    elif positives and negatives:
        print("No clean positive/negative separation; inspect a floor plus score margin.")


def _default_database() -> Path:
    url = os.environ.get("MEMORA_DATABASE_URL", "sqlite:///./memora.sqlite3")
    prefix = "sqlite:///"
    if not url.startswith(prefix) or not url[len(prefix):]:
        raise ValueError("MEMORA_DATABASE_URL must use sqlite:///path")
    return Path(url[len(prefix):])


if __name__ == "__main__":
    main()
