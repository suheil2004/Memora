# MVP architecture

## Why this shape

A modular monolith is the shortest path to a reliable hackathon demo. The Python package owns ingestion, memory, retrieval, and persistence behind typed interfaces; one API process can compose them later. SQLite plus a replaceable vector-store implementation is sufficient for local demos. Vendor choices remain outside the domain layer so an embedding API or local model can be selected during the first vertical slice without rewriting ingestion.

The extension is a thin client. Its site-specific behavior sits behind `ChatSiteAdapter`, and only one adapter will be implemented for the MVP. This prevents website DOM details from leaking into retrieval logic.

## Data flow

```text
User-provided export
  -> ConversationImporter (parse and normalize)
  -> Conversation + ordered Messages
  -> chunker
  -> ConversationChunks                 [raw conversation memory]
  -> EmbeddingService -> VectorStore

Conversation + Messages
  -> MemoryExtractor
  -> StructuredMemories                 [durable long-term memory]
  -> structured-memory repository

Current query from extension
  -> backend retrieval endpoint
  -> MemoryRetriever
       -> semantic search over ConversationChunks
       -> search StructuredMemories
       -> rank + deduplicate + enforce user scope
  -> ContextBuilder (relevance and size budget)
  -> compact, attributed Memora context block
  -> extension adapter makes it available to the active chat
```

## Data boundaries

`ConversationChunk` is source text with conversation/message provenance and an ordinal. It supports semantic retrieval and deletion with its source conversation. `StructuredMemory` is an extracted durable statement with a category, confidence, provenance, and lifecycle status. A structured memory never replaces or mutates its raw source.

All persisted entities are keyed by `user_id`. Implementations must filter by that key before ranking; filtering after vector retrieval risks cross-user disclosure. Context construction accepts an explicit character budget and emits provenance labels so results remain inspectable.

## Proposed final MVP tree

```text
memora/
├── AGENTS.md
├── README.md
├── .env.example
├── docs/architecture.md
├── backend/
│   ├── api/                 # routes, request/response schemas, composition root
│   ├── ingestion/           # importers, cleaning, chunking
│   ├── rag/                 # embeddings, vector retrieval, ranking, context
│   ├── memory/              # extraction, categories, deduplication, management
│   ├── database/            # SQLite schema and repositories
│   ├── models.py
│   └── settings.py
├── extension/
│   ├── src/adapters/        # interface + exactly one supported site
│   ├── src/background.ts
│   ├── src/content.ts
│   ├── manifest.json
│   └── package.json
└── tests/
    ├── ingestion/
    ├── rag/
    └── memory/
```

Empty implementation areas include a README so the intended boundary is visible until the next vertical slice fills it.

