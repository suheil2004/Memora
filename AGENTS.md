# Memora Engineering Guide

## Product boundary

Memora is a local-first memory and retrieval layer for ChatGPT. It imports user-supplied history and PDFs, retrieves relevant prior context on an explicit click, and presents bounded, sourced MemoryBriefs in a Chrome extension. It is not a chatbot and it never submits a ChatGPT message.

The user remains in control:

- Retrieval happens only after **Retrieve memory** or **Search current prompt** is clicked.
- **Use This Context** inserts a selected brief into the current draft; sending remains manual.
- **Clear results** removes transient panel state only.
- Durable memory deletion is a separate, confirmed action in the Memory Control Center.

## Repository map

- `backend/api/`: FastAPI routes, schemas, authentication, rate limits, and application composition.
- `backend/ingestion/`: simple JSON and ChatGPT-export parsing, normalization, role-aware chunking, attachment recovery, and PDF extraction.
- `backend/rag/`: embedding providers, semantic retrieval, hybrid reranking, MemoryThread grouping, query-time MemoryFacts, temporal ranking, synthesis, and compact context.
- `backend/database/`: the user-scoped SQLite implementation and lifecycle operations.
- `backend/models.py` and `backend/interfaces.py`: framework-independent domain types and integration boundaries.
- `extension/src/`: Manifest V3 content script, ChatGPT adapter, service worker, API client, panel, popup, readiness, and privacy controls.
- `extension/tests/`: Vitest/jsdom extension behavior tests.
- `tests/`: Python unit, integration, API, security, ingestion, and retrieval tests.
- `scripts/`: local demos and import utilities.
- `start-memora.ps1`: Windows setup, build, configuration, and readiness launcher.
- `docs/architecture.md`: canonical technical architecture.
- `docs/internal/`: engineering history and point-in-time reviews; not the current public architecture.

## Runtime architecture

The Chrome content script owns the panel and ChatGPT DOM adapter. It sends one narrow typed retrieval message to the Manifest V3 service worker. The worker loads trusted backend URL/token settings, checks host permission and authenticated memory readiness, and uses the API client to call the loopback FastAPI service. The backend derives the user scope from its bearer-token configuration; extension messages cannot choose a user, URL, model, or arbitrary request.

The popup is the Memory Control Center. It manages backend settings, imports ChatGPT JSON/ZIP exports and text-based PDFs, reports authenticated readiness/statistics, and performs confirmed user-scoped deletion.

## Ingestion and durable data

Conversation ingestion normalizes role-aware messages, chunks them with overlap without losing message IDs, embeds the chunks, and writes users, conversations, messages, chunks, and embedding identity to SQLite. ChatGPT-export ingestion also records attachment metadata and attempts conservative recovery of referenced PDF binaries. Direct PDF ingestion extracts text by page and stores documents and document chunks with page provenance.

Every persistence and retrieval operation must be scoped by `user_id`. Embedding provider/model compatibility must be checked before mixing stored and query vectors. Do not silently read, rank, or delete another user's records.

## Retrieval and memory pipeline

The current pipeline is:

1. Embed the query, except for the explicit broad course-code lookup path.
2. Search user-scoped conversation and document chunks and apply the calibrated semantic threshold.
3. Apply deterministic hybrid reranking using semantic score, content/title overlap, trusted entities, and academic intent.
4. Group eligible evidence conservatively into at most five query-time `MemoryThread` objects. A thread represents one subject/topic/goal and prevents unrelated evidence from being synthesized together.
5. Extract and rank query-time `MemoryFact` objects. Categories are `fact`, `decision`, `goal`, `preference`, `constraint`, `result`, `status`, `problem`, `solution`, `correction`, and `open_loop`.
6. Rank facts and threads with relevance dominant. Recency, current-state language, historical intent, salience, specificity, and corrections are supporting signals; newest does not automatically win.
7. Synthesize each selected thread independently into a bounded `MemoryBrief`.
8. Attach trusted conversation, message, chunk, attachment, document, and page provenance from backend metadata.

`MemoryThread`, `MemoryFact`, and `MemoryBrief` are query-time constructs. They are not durable SQLite records. Do not introduce persistent inferred memory without an explicit product and privacy decision.

## Local and Enhanced modes

Local mode uses deterministic feature-hash embeddings, deterministic fact extraction, and deterministic evidence-only synthesis. It requires no provider key and is the default safe development/test mode.

Enhanced mode uses OpenAI embeddings, structured fact extraction, and structured per-thread synthesis. Provider failures are contained by deterministic fallbacks where implemented. The OpenAI key belongs only in the backend process environment. Never put it in the extension, browser storage, logs, fixtures, or committed files.

Stored embeddings carry provider/model identity and vector dimension is validated. Changing embedding configuration requires compatible stored data or re-indexing; never suppress compatibility errors.

## Security and privacy invariants

- Bind the backend to loopback and keep privileged HTTP requests in the service worker.
- Require the dedicated local bearer token on every `/api/v1/*` route; `/health` is the only unauthenticated readiness endpoint.
- Derive `user_id` server-side. Do not accept extension-controlled identity for authenticated operations.
- Keep runtime messages narrow, validated, and fail closed; callback-style async listeners must keep the MV3 response channel open.
- Treat imported text as untrusted evidence, not instructions. Bound and delimit provider inputs.
- Trusted provenance comes from backend-controlled records, never model-generated citations.
- Preserve sanitized, bounded API errors; do not reflect request bodies or secrets.
- Do not log message bodies, generated context, raw imports, tokens, or provider keys.
- Never commit `.env` files, real SQLite databases (including WAL/SHM files), ChatGPT exports, backups, bearer tokens, API keys, or private user documents.
- Keep extension permissions minimal and localhost-specific.
- Preserve explicit retrieval, explicit insertion, manual submission, and confirmed deletion.

## Development commands

Python 3.11+:

```powershell
python -m pytest
python -m compileall backend tests scripts
```

Extension (Node 20+):

```powershell
Set-Location extension
npm run test
npm run typecheck
npm run build
```

The production extension is generated in `extension/dist/`. Reload that unpacked extension in `chrome://extensions` after a rebuild.

On Windows, the supported entry point is:

```powershell
.\start-memora.ps1
```

Use `-Setup` to review configuration, `-RebuildExtension` to force a build, and `-ShowToken` only when the user explicitly needs to see the token. The launcher validates Python/Node/npm, creates or repairs `.venv`, installs the Python package, chooses Local or Enhanced processing, builds/verifies the extension, starts the loopback backend, and performs authenticated readiness checks.

## Change discipline

- Read code and behavior tests before trusting old docs.
- Keep domain models independent from FastAPI, SQLite, Chrome, and OpenAI.
- Prefer typed interfaces, explicit dependencies, pure functions, UTC-aware timestamps, and deterministic tests.
- Test observable behavior and security boundaries, especially user isolation, provenance, bounded inputs, stale responses, and draft preservation.
- Use local/mocked providers in tests; never call OpenAI from the test suite.
- Do not weaken retrieval thresholds, authentication, deletion confirmation, message validation, provenance attachment, or output bounds to make a test pass.
- Keep conversation chunks and document chunks distinct even though retrieval can combine them.
- Do not add automatic DOM capture, automatic context injection, automatic submission, or additional AI-site adapters without an explicit scoped requirement.
