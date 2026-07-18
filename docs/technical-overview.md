# Memora Technical Overview

## Architecture

```text
ChatGPT
    |
    v
Memora Chrome Extension (content script + ChatGPT adapter)
    |
    v
Manifest V3 Service Worker
    |
    v
FastAPI Backend
    |
    v
Embedding Service
    |
    v
RAG Retriever
    |
    v
SQLite Memory Store
```

The ingestion path is separate:

```text
ChatGPT Export (JSON or ZIP)
    |
    v
ChatGPT Export Importer
    |
    v
Normalization
    |
    v
Message-Aware Chunking
    |
    v
Embeddings
    |
    v
SQLite Storage
```

Memora is a local modular monolith behind a thin browser extension. Domain interfaces keep the importer, embedding provider, vector store, retriever, and context builder replaceable without coupling them to FastAPI or Chrome.

## Retrieval Flow

The user types a draft in ChatGPT and explicitly clicks **Retrieve Memory**. The content script extracts the draft and sends a strictly validated runtime message to the background service worker. The worker loads the fixed-localhost backend URL and dedicated Memora token, then calls `POST /api/v1/context/retrieve`. The backend authenticates the token and derives the database scope from `MEMORA_USER_ID`.

```text
Current query
  -> query embedding
  -> user-scoped vector search
  -> cosine-similarity ranking
  -> content deduplication
  -> similarity threshold + top-k
  -> compact context builder
  -> service-worker response
  -> extension panel
```

SQLite selects chunks for the requested `user_id` before ranking. Results retain the user ID, conversation ID/title, chunk ID, and source message IDs. The context builder prioritizes higher-ranked results and enforces a configurable character budget.

## Conversation Ingestion

The explicit history-import endpoint accepts one or more JSON files or one ZIP. ZIP entries are inspected in memory and never extracted. Supported documents may contain a conversation array, a top-level `conversations` array, a single conversation, numbered JSON files, a ChatGPT message graph, or a supported flat message list.

For graph exports, the importer starts at `current_node`, follows parent links, reverses the resulting branch into chronological order, and falls back to the latest identifiable leaf when needed. It extracts supported user and assistant text, skipping internal roles and unsupported media while retaining stable source-derived identifiers.

A normalized SHA-256 fingerprint provides user-scoped duplicate detection. An unchanged import is skipped without recomputing embeddings. A conversation with the same ID but changed normalized content is saved and re-indexed.

## Embeddings

`LocalHashEmbeddingService` provides deterministic feature-hash vectors for offline tests and baseline evaluation. It requires no network or API key. `OpenAIEmbeddingService` uses `text-embedding-3-small` for semantic retrieval and batches document embeddings.

Every stored vector includes its embedding provider and model identity. Retrieval refuses to compare incompatible vector spaces and instructs the operator to re-index after a provider or model change.

## Storage

`SQLiteVectorStore` persists:

- users and user-scoped conversations;
- normalized messages and roles;
- chunks with ordered source-message provenance;
- serialized embeddings with provider/model metadata; and
- normalized import fingerprints.

Search loads the requested user's vectors and computes cosine similarity in the application process. This linear scan is simple and sufficient for the hackathon dataset, but it is not intended for large production indexes.

## Browser Extension

The extension uses Chrome Manifest V3:

- The content script manages the floating panel and current ChatGPT draft.
- `ChatGptAdapter` isolates site-specific DOM discovery and mutation.
- Typed runtime messages cross from the content script to the service worker.
- The service worker performs privileged localhost HTTP requests.
- The popup stores the fixed-localhost backend URL and Memora token, checks health, and uploads explicitly selected history files.

The OpenAI API key is never present in extension settings, messages, or bundles. The extension performs no automatic retrieval, conversation capture, prompt submission, analytics, or telemetry.

## Context Insertion

After a successful retrieval, the extension creates a snapshot containing the original query and compact context points. **Use This Context** labels history as untrusted reference data, escapes forged delimiter text, and encloses memory in `<historical_memory>` tags before the clearly separated current question. The insertion layer detects an already-inserted prompt and refuses to overwrite a changed draft. It never submits the message. This boundary reduces but cannot eliminate prompt-injection risk.

## Privacy and Security Boundaries

- Users explicitly select ChatGPT export files; Memora does not automatically read account history.
- The extension uploads selected files to the user's local FastAPI backend, not directly to OpenAI.
- The backend sends only text required for embeddings to the configured embedding provider.
- OpenAI API credentials remain in the backend process environment.
- Retrieval and insertion require separate user actions.
- Stored content, embeddings, databases, exports, and credentials are treated as sensitive and ignored by Git where applicable.
- API errors are sanitized, and production debug logging is disabled by default without logging query/context bodies.

Current boundaries are not complete production security: the local bearer token represents one configured user and is not a public multi-user authentication system; the local database is not encrypted; and end-to-end encryption is not implemented.

## Retrieval Evaluation

The repository includes 15 paraphrased queries across five synthetic topics. The local feature-hash baseline achieved 46.7% Top-1 accuracy. OpenAI `text-embedding-3-small` achieved 15/15 Top-1 and 15/15 Top-3 accuracy.

The local baseline emphasizes overlapping hashed lexical features, so it struggles when a query paraphrases a stored fact using different vocabulary. Semantic embeddings better align those related meanings. This small MVP dataset verifies the intended demo behavior; it does not establish general or production retrieval accuracy.

## Testing

- Backend behavior and integration tests: **37/37 passed**
- Extension Vitest/jsdom tests: **32/32 passed**
- Python compilation: **passed**
- TypeScript strict typecheck: **passed**
- Production extension build with esbuild: **passed**
- Manual browser flow through retrieval and explicit insertion: **verified**

Automated tests use deterministic local embeddings and do not depend on a live OpenAI request.

## Known Limitations

- The local FastAPI backend must be running.
- Local single-user bearer authentication is not sufficient for public/cloud multi-user deployment.
- ChatGPT DOM selectors are based on a non-public interface and may change.
- SQLite uses a linear vector scan.
- Large imports and indexing are synchronous.
- ChatGPT export schemas may evolve.
- ChatGPT is the only implemented AI chat adapter.
- Structured durable-memory extraction is architecturally separated but not active.
- End-to-end encryption and encrypted local storage are not implemented.
- History access requires an explicit user-supplied export.
