"""Run Memora's local import-to-context demo."""

import argparse
import tempfile
from pathlib import Path

from backend.database.sqlite_store import SQLiteVectorStore
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.json_importer import JsonConversationImporter
from backend.models import User
from backend.rag.context_builder import CompactContextBuilder
from backend.rag.local_embeddings import LocalHashEmbeddingService
from backend.rag.pipeline import index_conversation
from backend.rag.retriever import SemanticMemoryRetriever


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "query", nargs="?", default="How can I reduce inference latency on my project?"
    )
    parser.add_argument("--database", type=Path, help="SQLite path; defaults to a temporary demo DB")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-similarity", type=float, default=0.05)
    args = parser.parse_args()

    temporary = tempfile.TemporaryDirectory() if args.database is None else None
    database = args.database or Path(temporary.name) / "memora_demo.sqlite3"  # type: ignore[union-attr]
    user = User("demo-user", display_name="Demo User")
    importer = JsonConversationImporter()
    chunker = ConversationChunker(max_tokens=80, overlap_tokens=20)
    embeddings = LocalHashEmbeddingService()
    store = SQLiteVectorStore(database)

    root = Path(__file__).resolve().parents[1]
    for filename in ("drone_detection.json", "sourdough.json"):
        imported = importer.import_file(root / "samples" / filename, user_id=user.id)[0]
        index_conversation(
            imported, user=user, chunker=chunker, embeddings=embeddings, store=store
        )

    results = SemanticMemoryRetriever(embeddings, store).retrieve(
        args.query, user_id=user.id, limit=args.top_k, min_similarity=args.min_similarity
    )
    print(CompactContextBuilder().build(args.query, results, max_chars=1200))
    if temporary is not None:
        temporary.cleanup()


if __name__ == "__main__":
    main()
