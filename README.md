# Memora

Memora is a compact memory and RAG layer for existing AI chat applications. It supports deterministic local embeddings for offline development and OpenAI semantic embeddings for realistic retrieval.

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
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall backend tests

Set-Location extension
npm install
npm run typecheck
```

Offline tests use local embeddings and need no API key. The OpenAI implementation uses the official Python SDK and batches conversation chunks in one request.

## Embedding provider configuration

The demo reads environment variables directly. Local embeddings remain the default:

```powershell
$env:MEMORA_EMBEDDING_PROVIDER = "local"
python -m scripts.demo_rag
```

To use semantic embeddings, set the key in your shell and never commit it:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
$env:MEMORA_EMBEDDING_PROVIDER = "openai"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
python -m scripts.demo_rag
```

`.env.example` documents the available settings, but this dependency-light scaffold does not automatically load `.env` files. Stored vectors include provider and model metadata. Changing either value requires re-indexing; Memora raises a clear compatibility error rather than comparing different vector spaces.

## Run the retrieval demo

The demo imports both files in `samples/`, indexes them into a temporary SQLite database, runs the default latency query, and prints ranked chunks with scores, provenance, and compact context:

```powershell
python -m scripts.demo_rag
```

Use a custom query or retain the index for inspection:

```powershell
python -m scripts.demo_rag "How do I improve my bread crust?" --database .\memora.sqlite3
```

To import sample data programmatically, use `JsonConversationImporter`, then pass its result to `index_conversation`; the demo is the minimal executable example.

## Evaluate retrieval quality

The evaluation indexes five unrelated conversations and runs 15 paraphrased queries. Live OpenAI evaluation is explicit and consumes API credits:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
python -m scripts.evaluate_retrieval
```

Compare ranking accuracy between local and OpenAI embeddings:

```powershell
python -m scripts.evaluate_retrieval --provider local
$env:OPENAI_API_KEY = "your-api-key"
python -m scripts.evaluate_retrieval --provider both
```

The script prints every query, expected topic, top-three results, similarity scores, pass/fail status, and aggregate Top-1 and Top-3 accuracy. Absolute scores across providers are not compared because they come from different embedding spaces.

## Current status and limitations

The core models distinguish original searchable conversation chunks from extracted durable memories. Python `Protocol` contracts keep providers and retrieval logic independent. The local hashes provide reproducible lexical similarity, while OpenAI embeddings support semantic retrieval. SQLite still performs an in-process linear scan, suitable only for the hackathon-scale demo. The extension remains an untouched shell with no DOM behavior.
