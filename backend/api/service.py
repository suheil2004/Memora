"""Application service composing Memora's existing ingestion and RAG pipeline."""

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from backend.database.sqlite_store import (
    MemoryClearSummary, MemoryStatistics, SQLiteVectorStore,
)
from backend.ingestion.chunker import ConversationChunker
from backend.ingestion.json_importer import JsonConversationImporter
from backend.ingestion.bulk_import import BulkImportSummary, ChatGPTBulkImportService
from backend.ingestion.chatgpt_export import ChatGPTExportImporter
from backend.ingestion.pdf_documents import DocumentImportSummary, PDFDocumentImportService
from backend.interfaces import EmbeddingService, MemoryFactExtractor, MemorySynthesizer, RetrievalResult
from backend.models import MemoryBrief, MemoryThread, User
from backend.rag.context_builder import CompactContextBuilder
from backend.rag.pipeline import index_conversation
from backend.rag.relevance import minimum_relevance_similarity
from backend.rag.reranker import (
    HybridReranker, entity_dominant_course_code, extract_course_codes,
)
from backend.rag.memory_threads import MemoryThreadGrouper
from backend.rag.memory_facts import (
    DeterministicMemoryFactExtractor, temporal_thread_utility, thread_with_ranked_facts,
)
from backend.rag.synthesis import DeterministicMemorySynthesizer, synthesize_threads
from backend.rag.retriever import SemanticMemoryRetriever


@dataclass(frozen=True, slots=True)
class ImportSummary:
    conversation_id: str
    title: str | None
    chunks_indexed: int
    embedding_provider: str
    embedding_model: str


@dataclass(frozen=True, slots=True)
class ContextResponseData:
    query: str
    context: str
    results: tuple[RetrievalResult, ...]
    threads: tuple[MemoryThread, ...] = ()
    briefs: tuple[MemoryBrief, ...] = ()
    timing: "RetrievalTiming | None" = None


@dataclass(frozen=True, slots=True)
class RetrievalTiming:
    retrieval_ms: float
    reranking_ms: float
    thread_grouping_ms: float
    synthesis_ms: float
    total_ms: float


class MemoraService:
    def __init__(
        self,
        *,
        importer: JsonConversationImporter,
        chunker: ConversationChunker,
        embeddings: EmbeddingService,
        store: SQLiteVectorStore,
        context_builder: CompactContextBuilder,
        context_max_chars: int = 6000,
        synthesizer: MemorySynthesizer | None = None,
        fact_extractor: MemoryFactExtractor | None = None,
    ) -> None:
        self.importer = importer
        self.chunker = chunker
        self.embeddings = embeddings
        self.store = store
        self.context_builder = context_builder
        self.context_max_chars = context_max_chars
        self.relevance_min_similarity = minimum_relevance_similarity(embeddings)
        self.retriever = SemanticMemoryRetriever(embeddings, store)
        self.reranker = HybridReranker()
        self.thread_grouper = MemoryThreadGrouper()
        self.synthesizer = synthesizer or DeterministicMemorySynthesizer()
        self.fact_extractor = fact_extractor or DeterministicMemoryFactExtractor()

    def import_conversation(self, payload: dict[str, Any], *, user_id: str) -> ImportSummary:
        imported = self.importer.import_data(payload, user_id=user_id)[0]
        chunks = index_conversation(
            imported,
            user=User(user_id),
            chunker=self.chunker,
            embeddings=self.embeddings,
            store=self.store,
        )
        return ImportSummary(
            conversation_id=imported.conversation.id,
            title=imported.conversation.title,
            chunks_indexed=len(chunks),
            embedding_provider=self.embeddings.provider_name,
            embedding_model=self.embeddings.model_name,
        )

    def retrieve_context(
        self,
        query: str,
        *,
        user_id: str,
        top_k: int,
        min_similarity: float,
        max_context_chars: int | None = None,
    ) -> ContextResponseData:
        started = perf_counter()
        course_codes = extract_course_codes(query)
        course_code = next(iter(course_codes)) if len(course_codes) == 1 else None
        if course_code:
            broad_entity_lookup = entity_dominant_course_code(query) is not None
            query_embedding = None if broad_entity_lookup else self.embeddings.embed_query(query)
            candidates = self.store.search_course_scope(
                course_code,
                user_id=user_id,
                limit=max(100, top_k * 20),
                query_embedding=query_embedding,
                embedding_provider=self.embeddings.provider_name if query_embedding else None,
                embedding_model=self.embeddings.model_name if query_embedding else None,
            )
        else:
            candidates = self.retriever.retrieve(
                query,
                user_id=user_id,
                limit=max(20, top_k * 2),
                min_similarity=max(min_similarity, self.relevance_min_similarity),
            )
        retrieved = perf_counter()
        ranked_candidates = self.reranker.rank_candidates(query, candidates)
        reranked = perf_counter()
        grouped = self.thread_grouper.group(query, ranked_candidates, limit=5)
        grouped_at = perf_counter()
        enriched = [
            (*thread_with_ranked_facts(query, thread, self.fact_extractor), representative)
            for thread, representative in grouped
        ]
        reference_time = max(
            (timestamp for thread, _, _ in enriched for timestamp in thread.source_timestamps),
            default=None,
        )
        enriched.sort(key=lambda item: (
            -temporal_thread_utility(
                query, item[0], item[1], reference_time=reference_time,
            ),
            -item[0].strongest_hybrid_score,
            item[0].thread_id,
        ))
        selected = enriched[:min(top_k, 5)]
        fact_driven_threads = tuple(thread for thread, _, _ in selected)
        threads = fact_driven_threads
        results = tuple(representative for _, _, representative in selected)
        briefs = synthesize_threads(self.synthesizer, query, fact_driven_threads)
        synthesized = perf_counter()
        context = self.context_builder.build(
            query,
            results,
            max_chars=max_context_chars or self.context_max_chars,
        )
        timing = RetrievalTiming(
            retrieval_ms=(retrieved - started) * 1000,
            reranking_ms=(reranked - retrieved) * 1000,
            thread_grouping_ms=(grouped_at - reranked) * 1000,
            synthesis_ms=(synthesized - grouped_at) * 1000,
            total_ms=(perf_counter() - started) * 1000,
        )
        return ContextResponseData(query, context, results, threads, briefs, timing)

    def import_chatgpt_history(
        self,
        uploads: tuple[tuple[str, bytes], ...],
        *,
        user_id: str,
    ) -> BulkImportSummary:
        return ChatGPTBulkImportService(
            importer=ChatGPTExportImporter(),
            chunker=self.chunker,
            embeddings=self.embeddings,
            store=self.store,
        ).import_uploads(uploads, user_id=user_id)

    def import_documents(
        self, uploads: tuple[tuple[str, bytes, str | None], ...], *, user_id: str
    ) -> DocumentImportSummary:
        return PDFDocumentImportService(self.embeddings, self.store).import_uploads(
            uploads, user_id=user_id
        )

    def memory_statistics(self, *, user_id: str) -> MemoryStatistics:
        return self.store.memory_statistics(user_id=user_id)

    def clear_memory(self, *, user_id: str) -> MemoryClearSummary:
        return self.store.clear_user_memory(user_id=user_id)
