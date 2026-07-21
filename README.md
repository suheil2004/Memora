# Memora

**A user-controlled memory layer that brings relevant history into a new ChatGPT conversation without silently injecting or submitting anything.**

Long-running AI work becomes fragmented across old chats, changed plans, and attached documents. Memora imports history into a local memory service, retrieves the evidence relevant to the current draft, organizes it into sourced MemoryBriefs, and lets the user decide what to carry forward.

Memora is a local-first hackathon MVP, not a standalone chatbot or a production multi-user service.

## See Memora in action

<img src="docs/assets/memora-panel.png" alt="Memora panel showing a sourced MemoryBrief" width="760">

*Relevant historical evidence is organized into concise, sourced MemoryBriefs.*

<img src="docs/assets/memora-use-this-context.png" alt="Memora context inserted into the ChatGPT composer after explicit user selection" width="760">

*The user selects Use This Context; Memora updates the draft but never submits it.*

<img src="docs/assets/memora-privacy-readiness.png" alt="Memora popup showing authenticated readiness and privacy controls" width="760">

*Authenticated readiness, local memory statistics, imports, and explicit deletion controls.*

## Core features

- Explicit ChatGPT JSON/ZIP history import with normalized, role-aware chunks.
- Conservative attachment metadata recovery and indexing of safely resolved text PDFs.
- Local, user-scoped SQLite storage for conversations, chunks, vectors, documents, and provenance.
- Semantic candidate retrieval followed by deterministic hybrid reranking.
- MemoryThreads that keep different subjects, tasks, courses, and versions separate.
- Query-time MemoryFacts ranked for relevance, salience, specificity, and temporal intent.
- One sourced MemoryBrief per selected thread, with deterministic fallbacks.
- **Best match** and **Most recent** views, trusted timestamps, and provenance.
- Sticky repeated-search controls: **Showing memory for**, **Search current prompt**, and **Clear results**.
- Explicit **Use This Context** insertion with changed-draft protection and no automatic submission.
- Authenticated readiness, memory statistics, and user-scoped deletion in **Privacy & Memory**.
- Enhanced and Local processing modes through a Windows-first launcher.

## How it works

```text
User-selected history and PDFs
  -> normalization and role-aware chunking
  -> embeddings and user-scoped SQLite
  -> semantic candidates and hybrid reranking
  -> MemoryThreads
  -> ephemeral query-time MemoryFacts
  -> temporal/current-state prioritization
  -> per-thread MemoryBriefs with backend-attached provenance
  -> explicit user-selected insertion
  -> manual ChatGPT submission
```

The ChatGPT content script sends typed messages to a Manifest V3 service worker. The service worker—not the page content script—calls the authenticated localhost FastAPI backend. Provider credentials remain in the backend environment.

## Why more than vector search

Vector similarity identifies candidate chunks. Memora then applies lexical and entity-aware reranking, groups compatible evidence into separate MemoryThreads, extracts bounded MemoryFacts for the current query, interprets current versus historical intent, handles explicit corrections, synthesizes each thread independently, and attaches trusted provenance outside model output.

MemoryFacts are currently ephemeral query-time objects; they are not a durable stored memory table.

## Quick start

Requirements: Windows PowerShell 5.1 or newer PowerShell, Python 3.11+, Node.js 20+ with npm, and Google Chrome.

```powershell
.\start-memora.ps1
```

The launcher validates runtimes, repairs or creates `.venv`, installs dependencies, configures Enhanced or Local mode, creates a stable local authentication token, builds the extension, starts FastAPI on `127.0.0.1:8765`, and checks authenticated readiness.

Chrome still requires a one-time unpacked-extension installation from `extension/dist`. See [the setup guide](docs/SETUP.md) for first-run instructions, import steps, testing, and troubleshooting.

## Full product overview

Read [docs/PRODUCT.md](docs/PRODUCT.md) for the complete product workflow, memory pipeline, provider boundaries, architecture, and honest MVP limitations.

## Built with Codex and GPT-5.6

Memora was developed through human-directed collaboration with Codex and GPT-5.6.

- **Codex** performed repository implementation, refactoring, test creation, debugging, launcher development, security hardening, extension UX work, and documentation verification under explicit human review.
- **GPT-5.6** supported product and architecture reasoning, MemoryThread/MemoryFact design, retrieval and temporal-ranking iteration, debugging strategy, defensive review, UX decisions, and documentation planning.

These models were used to build Memora. GPT-5.6 is not a required Memora runtime dependency. Enhanced mode currently uses separately configured OpenAI runtime providers; Local mode does not call OpenAI.

## Testing

Automated tests use deterministic local implementations or mocked providers and do not call OpenAI.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall backend scripts tests

Set-Location extension
npm run test
npm run typecheck
npm run build
```

Latest verification for this documentation audit:

- Backend tests: **101 passed**
- Extension tests: **78 passed**
- Python compilation: passed
- TypeScript strict typecheck: passed
- Production extension build: passed
- npm audit: 0 known vulnerabilities at the time checked

## Security and privacy

Memora uses a loopback-only backend, a dedicated local bearer token, server-derived user scope, bounded request/import handling, safe DOM text rendering, and explicit retrieval/insertion/deletion actions. Local SQLite data and saved `.env` credentials are not encrypted by Memora, and OpenAI-backed Enhanced mode sends bounded text to the configured provider.

See [SECURITY.md](SECURITY.md) for scope and vulnerability reporting.

## License

No license file is currently included. Unless a license is added, the repository should not be assumed to grant reuse rights.
