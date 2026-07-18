# Memora MVP Architecture

Memora is a local modular monolith plus a thin Manifest V3 extension. This document describes the code that exists today; it is not a future architecture plan.

## Runtime components

```text
ChatGPT draft
  -> content script / ChatGptAdapter
  -> chrome.runtime message
  -> background service worker
  -> Authorization: Bearer <Memora local token>
  -> POST http://127.0.0.1:8765/api/v1/context/retrieve
  -> FastAPI MemoraService
  -> query embedding + user-scoped SQLite cosine search
  -> ranked/deduplicated chunks + CompactContextBuilder
  -> background response
  -> Memora panel
  -> explicit Use This Context action
  -> updated draft (never auto-submitted)
```

The content script never calls the backend directly. Cross-origin HTTP runs in the service worker using manifest host permissions. Sensitive endpoints authenticate a dedicated local bearer token and derive database scope from server-side `MEMORA_USER_ID`. OpenAI keys stay in the backend process.

## Ingestion

```text
User-selected ChatGPT JSON/ZIP
  -> extension popup
  -> POST /api/v1/import/chatgpt
  -> ChatGPTExportImporter
  -> normalized Conversation + ordered Messages
  -> ConversationChunker
  -> EmbeddingService
  -> SQLiteVectorStore
```

ZIP entries are inspected in memory and are not extracted. The importer reconstructs the active branch of ChatGPT graph exports, accepts supported flat formats, skips unsupported content, and preserves source provenance. A user-scoped normalized fingerprint skips unchanged re-imports; changed conversations replace their prior chunks.

The direct `POST /api/v1/conversations/import` endpoint accepts Memora's documented single-conversation JSON shape.

## Raw conversation RAG

`ConversationChunk` is the active retrieval unit. It retains user ID, conversation ID/title, chunk ID/ordinal, text, and source message IDs. Chunk text preserves message roles. Embeddings are created by either:

- `OpenAIEmbeddingService` for semantic demo retrieval; or
- `LocalHashEmbeddingService` for deterministic offline tests and a lexical baseline.

The selected provider and model are stored with vectors. Memora rejects retrieval across incompatible vector spaces so changing provider/model requires re-indexing.

`SQLiteVectorStore` filters by `user_id` before cosine ranking. `SemanticMemoryRetriever` applies the similarity threshold, ranking, limit, and deduplication. `CompactContextBuilder` prioritizes higher-ranked chunks and enforces a character budget.

## Browser extension

- `ChatGptAdapter` isolates ChatGPT DOM selectors and draft mutation.
- `content.ts` owns explicit retrieve/use actions and panel state.
- `messaging.ts` defines the content-to-background request path.
- `background-listener.ts` keeps the asynchronous response channel open.
- `background-handler.ts` loads settings, checks host permission, and invokes the API client.
- `popup.ts` owns settings, health status, and explicit history import.

Retrieval does not capture the current conversation, run automatically, inject automatically, or submit messages. If the draft changes after retrieval, insertion is refused to protect the user's edits. Inserted history is labeled untrusted reference data and enclosed in escaped `<historical_memory>` delimiters.

## Storage and privacy boundaries

Every persisted conversation, chunk, fingerprint, and retrieval query is scoped by the authenticated server-configured `MEMORA_USER_ID`; clients cannot choose it. The dedicated local token is a single-user hackathon control, not production authentication. Conversation content and embeddings are sensitive local data; the SQLite file is ignored by Git and should not be shared.

The domain includes structured-memory models/interfaces as a future boundary, but the current vertical slice retrieves raw conversation chunks only. No structured-memory extraction or combined retrieval is active.

## Operational limits

- One local FastAPI process and SQLite database
- Linear in-process vector scan
- Synchronous import/indexing
- One ChatGPT adapter with selectors that may require maintenance
- Localhost backend permissions only
- Dedicated local bearer authentication and in-process abuse limits; no production multi-user authentication
- Query limit 2,000 characters, `top_k` 1–10, and at most 10 selected import files
- No encryption, background queue, cloud deployment, telemetry, or analytics
