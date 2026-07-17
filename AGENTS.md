# Memora Engineering Guide

## Product

Memora is a personalized memory and retrieval layer for existing AI chat applications. It imports a user's prior conversations, retrieves only the context relevant to a new query, and exposes that compact context to a supported chat experience. It is not a standalone chatbot.

## MVP scope

- Import user-supplied conversation exports or files.
- Normalize messages and split conversations into searchable chunks.
- Embed and store raw conversation chunks.
- Extract and store durable structured memories separately.
- Retrieve, rank, deduplicate, and compact relevant context.
- Expose retrieval through a Python backend.
- Provide one Chrome Manifest V3 extension adapter.
- Let later iterations inspect and delete stored memories.

## Architecture

- `extension/`: TypeScript Chrome extension and site-adapter boundary.
- `backend/`: Python package containing domain models and service boundaries.
- `backend/ingestion/`: import, cleaning, and chunking.
- `backend/rag/`: embeddings, vector search, ranking, and context building.
- `backend/memory/`: structured-memory extraction and retrieval.
- `backend/database/`: persistence implementations and repositories.
- `tests/`: behavior-focused unit and integration tests.
- `docs/`: architecture and decisions.

Raw conversation chunks and structured long-term memories are different data types and storage concerns. Retrieval may combine them, but ingestion and lifecycle management must not blur the boundary.

## Coding conventions

- Target Python 3.11+ and TypeScript in strict mode.
- Keep domain models independent of web frameworks, databases, and vendors.
- Express integration boundaries with typed protocols/interfaces.
- Use UTC-aware timestamps and UUID strings at system boundaries.
- Prefer small pure functions, explicit dependencies, and immutable value objects where practical.
- Add tests for observable behavior; do not test that a protocol merely exists.
- Keep retrieved context bounded and label its provenance.
- Avoid dependencies until an implementation needs them.

## Privacy principles

- Treat conversation content, embeddings, and inferred memories as sensitive user data.
- Collect and retain only what is needed for retrieval.
- Never log message bodies, generated context, secrets, or raw imports by default.
- Preserve provenance so users can understand why a memory exists.
- Design every stored record to support user-scoped inspection and deletion.
- Enforce user isolation in every persistence and retrieval implementation.
- Keep secrets in environment variables; never commit them.

## Explicitly out of scope for the first MVP

- A standalone chat UI or model.
- Browser DOM scraping and automatic prompt injection.
- Multiple AI-site implementations (define an adapter; implement one later).
- Undocumented access to historical ChatGPT conversations.
- Full end-to-end encryption, account billing, teams, or enterprise administration.
- Distributed services, queues, elaborate agent workflows, or premature scaling.
- Dumping whole conversation histories into a model context.

