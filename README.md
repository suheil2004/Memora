# Memora

Memora is a compact memory and RAG layer for existing AI chat applications. Its first vertical slice imports a conversation file, creates message-aware chunks, generates deterministic local embeddings, stores them in SQLite, retrieves relevant chunks, and constructs bounded context.

## Repository layout

```text
backend/                 Python domain and service boundaries
  database/              SQLite persistence and vector search
  ingestion/             import, normalization, and chunking
  memory/                structured long-term memory
  rag/                   embeddings, retrieval, and context construction
extension/               Manifest V3 TypeScript extension
  src/adapters/           chat-site adapter interface and initial placeholder
tests/                   Python tests
docs/architecture.md     data flow and design decisions
```

## Conversation JSON format

Each import file contains exactly one conversation. `conversation_id` and a non-empty `messages` array are required. Each message requires a supported `role` (`user`, `assistant`, `system`, or `tool`) and non-empty `content`. Timestamps are optional ISO 8601 values with a timezone.

```json
{
  "conversation_id": "conv_001",
  "title": "Drone Detection Project",
  "created_at": "2026-07-01T12:00:00Z",
  "messages": [
    {"role": "user", "content": "I am building a drone detection system."},
    {"role": "assistant", "content": "What hardware are you using?"}
  ]
}
```

## Local setup and tests

Requirements: Python 3.11+ and, only for extension type checking, Node.js 20+.

```powershell
Copy-Item .env.example .env
# The Python vertical slice has no third-party dependencies.
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall backend tests

Set-Location extension
npm install
npm run typecheck
```

No environment values or API keys are needed. Future provider credentials belong in `.env`, which is ignored.

## Run the retrieval demo

The demo imports both files in `samples/`, indexes them into a temporary SQLite database, runs the default latency query, and prints compact context:

```powershell
python -m scripts.demo_rag
```

Use a custom query or retain the index for inspection:

```powershell
python -m scripts.demo_rag "How do I improve my bread crust?" --database .\memora.sqlite3
```

To import sample data programmatically, use `JsonConversationImporter`, then pass its result to `index_conversation`; the demo is the minimal executable example.

## Current status and limitations

The core models distinguish original searchable conversation chunks from extracted durable memories. Python `Protocol` contracts keep importers, embeddings, stores, retrieval, and context assembly replaceable. The current hashed embeddings provide reproducible lexical similarity, not production semantic quality. SQLite performs an in-process linear scan, which is suitable only for the hackathon-scale demo. The extension remains an untouched shell with no DOM behavior.
