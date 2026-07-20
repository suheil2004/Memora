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

Retrieval applies an embedding-space-specific minimum cosine floor before context construction. The request's `min_similarity` may make this gate stricter but cannot lower the calibrated provider floor. Known local hash spaces have measured development defaults. Semantic and unknown providers require an explicit `MEMORA_RELEVANCE_MIN_SIMILARITY` measured with the read-only `scripts.calibrate_relevance` diagnostic; their score distributions are not assumed equivalent. If no chunk clears the gate, the API returns HTTP 200 with empty `results` and an empty `context`; the extension presents this as a valid “No relevant memory found” state rather than a retrieval failure. Stored provider/model metadata must exactly match the active embedding service, and vector dimensions must agree, so incompatible embedding spaces fail clearly instead of being silently ranked.

For precision on larger histories, ordinary semantic search returns up to 20 eligible candidates internally. The deterministic reranker computes `0.75 × cosine similarity + 0.15 × significant content overlap + 0.10 × title overlap + 0.30 × exact course-code match − 0.25 × explicit course-code mismatch + 0.08 × academic-intent overlap`, with a `0.12` document-evidence bonus when the query explicitly asks about a document, exam, question, lecture, or file. The semantic threshold remains the eligibility gate for ordinary queries. A query containing exactly one strict course code instead establishes a user-scoped course boundary from trusted title/message/chunk evidence; task intent and embeddings rank evidence only within that scope. Exact validated entity membership is the narrow documented exception to the semantic floor.

Reranked evidence is then organized into up to five internal Memory Threads before context construction. A thread retains its subject, topic/goal signature, strongest cosine and hybrid scores, supporting chunk text, conversation/chunk/message provenance, and available conversation timestamps. Different conversations remain separate by default. Cross-conversation evidence merges only when it has the same explicit subject and at least two strongly overlapping non-generic goal terms; unknown subjects never merge across conversations. Explicit version markers such as “old” and “updated” prevent merging, and even chunks from one conversation remain separate when their explicit subjects differ. Thread IDs are deterministic hashes of sorted supporting chunk IDs. The API preserves its legacy fields and additionally projects each selected thread as a sanitized user-facing memory brief.

An internal synthesis stage converts each selected thread into one separate `MemoryBrief`. With `MEMORA_SYNTHESIS_PROVIDER=openai`, the backend uses `MEMORA_SYNTHESIS_MODEL` and a Pydantic-validated Structured Outputs response containing only a proposed title, summary, and key details. The prompt treats historical text as untrusted, escapes evidence delimiters, and never includes multiple threads in one request. Memora—not the model—attaches trusted provenance. Provider/refusal/timeout/malformed-output failures fall back independently to a short deterministic evidence excerpt, so other thread briefs survive. The default provider remains `deterministic` for offline development and tests.

## Browser Extension

The extension uses Chrome Manifest V3:

- The content script manages the floating panel and current ChatGPT draft.
- `ChatGptAdapter` isolates site-specific DOM discovery and mutation.
- Typed runtime messages cross from the content script to the service worker.
- The service worker performs privileged localhost HTTP requests.
- The popup stores the fixed-localhost backend URL and Memora token, checks health, and uploads explicitly selected history files.

The OpenAI API key is never present in extension settings, messages, or bundles. The extension performs no automatic retrieval, conversation capture, prompt submission, analytics, or telemetry.

## Context Insertion

After successful retrieval, the extension renders up to five synthesized cards. The top memory is expanded; related memories have collapsible details. Each card's **Use This Context** action inserts only that brief, labels it as untrusted reference data, escapes forged delimiter text, and encloses it in `<memory_context>` tags before the clearly separated current question. The insertion layer detects an already-inserted prompt and refuses to overwrite a changed draft. It never submits the message. This boundary reduces but cannot eliminate prompt-injection risk.

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

The repository includes 15 paraphrased positive queries across five synthetic topics and five synthetic negative/no-match queries. The local feature-hash baseline achieved 46.7% positive Top-1 accuracy and 5/5 negative abstention with its calibrated floor. OpenAI `text-embedding-3-small` previously achieved 15/15 positive Top-1 and 15/15 positive Top-3 accuracy; live OpenAI evaluation remains opt-in and is not run by automated tests.

The local baseline emphasizes overlapping hashed lexical features, so it struggles when a query paraphrases a stored fact using different vocabulary. Semantic embeddings better align those related meanings. This small MVP dataset verifies the intended demo behavior; it does not establish general or production retrieval accuracy.

## Testing

- Backend behavior and integration tests: **83/83 passed**
- Extension Vitest/jsdom tests: **43/43 passed**
- Python compilation: **passed**
- TypeScript strict typecheck: **passed**
- Production extension build with esbuild: **passed**
- Manual browser flow through retrieval and explicit insertion: **verified**

Automated tests use deterministic local embeddings and do not depend on a live OpenAI request.

## User-facing memory briefs

The retrieval API preserves the legacy `query`, `context`, and `results` fields and adds a bounded `memories` list. Each memory exposes only its thread ID, display title, subject, synthesized summary, key details, trusted conversation ID/title sources, and whether deterministic fallback synthesis was used. Internal relevance scores, raw evidence, chunk IDs, message IDs, and provider errors are not part of the primary memory-card contract.

The extension renders up to five separate cards: the top memory is expanded and related memories have collapsible details. Each card inserts only its own synthesized brief inside an untrusted `<memory_context>` boundary; it never inserts all retrieved threads together and never submits the draft. Retrieval timing is measured internally by stage without logging private content or displaying timing diagnostics to users.

## Document Memory

Text-based PDFs are extracted locally with `pypdf` under configurable file-count, byte, page, text, and chunk limits. Additive `documents` and `document_chunks` tables preserve SHA-256 deduplication, sanitized filename, optional parent conversation, page provenance, and embedding metadata without rebuilding existing conversation indexes. Unified retrieval ranks conversation and document chunks together. PDF evidence remains untrusted inside the existing synthesis boundary, and public sources expose only document ID, filename, page range, and optional parent conversation—not paths or binary content. OCR, encrypted PDFs, remote URLs, and arbitrary embedded assets are unsupported.

Automatic Attachment Memory follows the real ChatGPT export schema: `metadata.attachments` supplies conversation/message provenance, `library_files.json` supplies origin and file metadata, `conversation_asset_file_names.json` maps opaque exported names to original names, and `export_manifest.json` locates archive entries. Resolution uses exact IDs before unique metadata matches and refuses ambiguity. The additive `attachments` table also preserves metadata-only records. Manual PDF upload is an optional additional-document workflow.

Large extracted exports can be imported locally with `python -m scripts.import_chatgpt_export <directory>`. Required database/user/provider configuration comes exclusively from the existing environment variables. The command performs an embedding-identity preflight, applies additive migrations, processes numbered shards incrementally, and emits only aggregate statistics and bounded error categories.

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
