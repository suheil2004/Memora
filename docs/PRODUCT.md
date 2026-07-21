# Memora Product Overview

## What Memora is

Memora is a user-controlled memory and retrieval layer for ChatGPT. It does not replace ChatGPT and is not a standalone chatbot. It imports history the user explicitly supplies, retrieves evidence relevant to a new draft, organizes that evidence into concise MemoryBriefs, and lets the user choose whether to insert one into the draft.

The current implementation is a local-first hackathon MVP: a Manifest V3 Chrome extension, a loopback FastAPI service, and a user-scoped SQLite database.

## The problem

Useful context becomes scattered across long-running conversations and separate chat sessions. A decision may be buried in an old project chat, a later conversation may correct it, and a supporting document may exist only as an attachment. A new conversation lacks that continuity and may confuse the original plan with the current one.

Dumping an entire history into a prompt is expensive, noisy, and difficult to audit. Nearest-vector retrieval alone can also blend different people, tasks, courses, or versions.

## The solution

Memora retrieves a bounded evidence set and adds several organization stages before presenting anything to the user. It keeps distinct topics and versions separate, prioritizes concrete and temporally appropriate facts, creates one brief per selected thread, and shows where each brief came from.

Nothing is inserted automatically. The user reviews the result, selects **Use This Context**, reviews the changed draft, and submits manually.

## Core workflow

1. The user imports a supported ChatGPT JSON/ZIP export or additional text PDFs through the extension popup.
2. Memora normalizes conversations, preserves message roles, creates overlapping chunks, embeds them, and stores them locally.
3. In ChatGPT, the user writes a draft question and explicitly selects **Retrieve memory**.
4. The extension service worker sends the query to the authenticated local API.
5. Memora retrieves candidates, reranks them, forms MemoryThreads, extracts query-time MemoryFacts, applies temporal/current-state reasoning, and creates MemoryBriefs.
6. The panel displays up to five cards with trusted conversation, attachment, or PDF/page provenance.
7. The user may change sorting, search the latest composer text, clear transient results, or select **Use This Context**.
8. Memora inserts only the selected brief into the unchanged draft. The user remains responsible for reviewing and manually submitting it.

Memora does not automatically capture the current conversation, automatically retrieve, automatically insert, or press Send.

## Memory intelligence pipeline

### Durable stored data

The active SQLite store persists user-scoped conversations, normalized messages, conversation chunks, embeddings and provider identity, import fingerprints, attachment metadata, documents, document chunks, timestamps, and provenance. It does not persist MemoryFacts as durable records.

### Retrieval

The configured embedding provider embeds imports and queries. SQLite filters by the authenticated server-configured user before cosine-similarity ranking. Provider, model, and vector dimensions must remain compatible; Memora rejects incompatible vector spaces rather than comparing them.

A calibrated minimum similarity threshold controls semantic eligibility. Exact single-course queries have a separate conservative course-scoping path derived from trusted stored content.

### Hybrid ranking

Only eligible candidates enter deterministic reranking. The reranker combines semantic similarity with significant query-term and title overlap, plus entity/course-aware adjustments. Diversity logic prevents a single conversation from flooding the result set.

### MemoryThreads

MemoryThreads conservatively group evidence belonging to the same subject and goal. Explicitly different people, courses, tasks, projects, and version markers remain separate. At most five final threads proceed to synthesis.

MemoryThreads are query-time organization objects, not a separate durable storage table.

### MemoryFacts

Each selected thread produces bounded, user-centric MemoryFacts such as decisions, constraints, preferences, results, status, corrections, and open loops. Facts are ranked by query relevance, salience, specificity, entity overlap, gentle recency, and temporal intent.

Near-duplicates collapse. A sufficiently related explicit correction may supersede an older claim while retaining combined provenance; unresolved conflicts remain visible. MemoryFacts are ephemeral for the request and are not persisted.

### Temporal and current-state reasoning

Memora uses trusted source timestamps and explicit language such as current, updated, switched, original, or previous. For ordinary queries, current-state evidence receives a preference and older-version markers a small penalty. For explicitly historical questions, historical markers receive the stronger preference. Recency is a supporting signal, not an eligibility rule.

Older databases created before source timestamps were indexed may require re-import or the user-scoped timestamp backfill utility before temporal evaluation.

### MemoryBriefs and provenance

Each final thread is synthesized independently into a MemoryBrief with a title, summary, and key details. Enhanced mode uses structured OpenAI synthesis with deterministic fallback; Local mode uses deterministic synthesis.

Conversation IDs/titles, message/chunk provenance, attachment metadata, document/page sources, subject, and timestamps are attached by trusted backend code rather than accepted from model output.

## Retrieval experience

- **Best match** preserves backend relevance order.
- **Most recent** reorders the already-returned cards by trusted latest timestamp without another API request.
- **Showing memory for** records the query that produced the visible cards; editing the composer does not silently change it.
- **Search current prompt** reads the composer at click time and replaces the previous cards through the existing retrieval path.
- **Clear results** removes only transient panel state. It does not call the backend, change the composer, or delete stored memory.
- Staged messages—**Searching previous conversations...**, **Organizing the strongest matches...**, and **Preparing concise memory cards...**—are elapsed-time UI feedback, not streamed backend progress.
- A request-generation guard prevents an older delayed response from replacing newer results.

## Documents and attachments

Supported ChatGPT exports can contain message attachment metadata, library records, filename mappings, manifest entries, and opaque assets. Memora correlates these conservatively: strong identifiers take priority, ambiguous mappings are refused, and archive entries are inspected without extracting the ZIP to disk.

Safely resolved text PDFs are signature-checked, bounded, extracted locally with `pypdf`, chunked, embedded, and cited with filename and page range. Attachments that cannot be resolved safely remain metadata-only records rather than guessed document content.

The popup also supports explicit import of additional text PDFs. Scanned/image-only PDFs, OCR, encrypted PDFs, remote URLs, and arbitrary embedded document formats are not supported.

For very large already-extracted ChatGPT exports, an explicit local CLI processes numbered conversation shards and resolved assets from a validated directory. The HTTP API and extension do not accept arbitrary filesystem paths.

## Privacy and user control

- The backend runs on loopback and stores imported memory in the configured local SQLite file.
- Sensitive routes require a dedicated local bearer token. User scope is derived from backend `MEMORA_USER_ID`, not a request field.
- The token is stored in the local Chrome profile; the OpenAI API key stays in the backend environment.
- Import, retrieval, insertion, submission, and deletion are distinct explicit actions.
- **Privacy & Memory** displays authenticated aggregate counts and can delete the configured user's active conversations, chunks, attachments, documents, fingerprints, and user row.
- Deletion does not erase backups, copied databases, source exports, provider-held data, or text already inserted into ChatGPT.

Local storage is not the same as exclusively local processing. Enhanced mode sends bounded content to configured OpenAI services. Memora does not claim end-to-end encryption, zero-knowledge processing, forensic secure erasure, or production identity.

## Enhanced and Local modes

| Capability | Enhanced mode | Local mode |
| --- | --- | --- |
| Embeddings | OpenAI semantic embeddings | Deterministic local feature-hash embeddings |
| MemoryFacts | OpenAI structured extraction with deterministic fallback | Deterministic local extraction |
| MemoryBriefs | OpenAI structured synthesis with deterministic fallback | Deterministic local synthesis |
| API key | Required | Not required |
| Intended use | Best intended demo quality | Offline development, tests, and zero-cost evaluation |

The modes do not promise identical retrieval or synthesis quality. Changing embedding provider/model requires a compatible index or deliberate re-indexing. OpenAI semantic retrieval also requires an explicitly calibrated `MEMORA_RELEVANCE_MIN_SIMILARITY`; the launcher does not invent a universal value.

## Architecture

Memora is a modular Python application behind a thin Chrome extension:

- `backend/ingestion`: JSON/ChatGPT imports, attachment recovery, PDF extraction, normalization, chunking.
- `backend/rag`: embeddings, retrieval, reranking, MemoryThreads, MemoryFacts, temporal utility, synthesis, context construction.
- `backend/database`: SQLite persistence and user-scoped lifecycle operations.
- `backend/api`: FastAPI schemas, authentication, rate limits, sanitized errors, and service composition.
- `extension`: ChatGPT adapter, panel, popup, typed runtime messaging, background service worker, API client, and privacy controls.
- `scripts`: demo/evaluation utilities, timestamp backfill, calibration, and extracted-export import.

The public API exposes unauthenticated `GET /health`; authenticated memory statistics, memory deletion, conversation import, ChatGPT export import, PDF import, and context retrieval routes.

## Why Memora is more than vector search

Memora still begins with embeddings and cosine similarity, but the product behavior comes from the stages after candidate retrieval:

- lexical and entity-aware hybrid reranking;
- conservative topic, subject, task, course, and version separation;
- bounded fact extraction with salience and specificity;
- explicit correction and current/historical handling;
- per-thread synthesis instead of blending unrelated evidence;
- backend-attached provenance and timestamps;
- user review before context insertion.

These are implemented deterministic and provider-backed mechanisms, not a claim that the system has solved general memory reasoning.

## Current MVP limitations

- Windows-first launcher and manual unpacked Chrome installation.
- One ChatGPT DOM adapter whose selectors may require maintenance.
- Local single-user capability token rather than production identity.
- SQLite linear vector scan and synchronous import/indexing, intended for demo-scale use.
- No encryption-at-rest guarantee, cloud deployment, background queue, telemetry, or analytics.
- Enhanced query-time fact extraction and per-thread synthesis can add provider latency and cost.
- Indirect prompt injection can be reduced but not eliminated.
- Attachment recovery is deliberately conservative, and OCR is not implemented.
- MemoryFacts and MemoryThreads are query-time objects rather than durable user-editable memory records.
- No complete Memora-versus-basic-RAG benchmark or production-scale evaluation currently exists.
