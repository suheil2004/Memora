# Memora

Memora is a personalized memory layer for AI that retrieves relevant context from your previous conversations.

## The Problem

AI assistants lose context across sessions. People repeatedly re-explain projects, preferences, decisions, and history even when those details already exist in older conversations.

## The Solution

Memora imports previous AI conversations, splits them into provenance-preserving chunks, and uses semantic retrieval to select only the history relevant to the current draft. A Chrome extension lets the user explicitly retrieve and insert that compact context into ChatGPT.

## Demo Flow

```text
Old conversations -> Memora -> semantic retrieval -> fresh ChatGPT conversation
                                                     -> Retrieve Memory
                                                     -> Use This Context
```

## Key Features

- ChatGPT JSON/ZIP history import with duplicate protection
- OpenAI semantic embeddings and deterministic offline embeddings
- User-scoped SQLite storage, ranking, deduplication, and provenance
- Compact, size-bounded context construction
- Manifest V3 Chrome extension with explicit retrieval and insertion
- No automatic capture, injection, submission, analytics, or telemetry

## Architecture

```text
ChatGPT
  |
Memora Chrome Extension
  |
FastAPI
  |
Embedding Service
  |
RAG Retriever
  |
SQLite Memory Store
```

History ingestion follows a separate path:

```text
ChatGPT Export -> Importer -> Normalizer -> Chunker -> Embeddings -> SQLite
```

See [docs/architecture.md](docs/architecture.md) for the implemented boundaries and data flow.

## Retrieval Evaluation

On the repository's small 15-query MVP evaluation dataset:

- Local feature-hash baseline Top-1: **46.7%**
- OpenAI `text-embedding-3-small` Top-1: **100%**
- OpenAI `text-embedding-3-small` Top-3: **100%**

This is a demo regression dataset, not a production benchmark. Live OpenAI evaluation is opt-in and consumes API credits:

```powershell
python -m scripts.evaluate_retrieval --provider local
$env:OPENAI_API_KEY = "your-api-key"
python -m scripts.evaluate_retrieval --provider openai
```

## Local Setup

Requirements: Python 3.11+, Node.js 20+, npm, and Chrome.

### Backend

1. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   python -m pip install -e .
   ```

3. Configure semantic embeddings in the current shell. The repository does not automatically load `.env`:

   ```powershell
   $env:OPENAI_API_KEY = "your-api-key"
   $env:MEMORA_EMBEDDING_PROVIDER = "openai"
   $env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
   $env:MEMORA_DATABASE_URL = "sqlite:///./memora.sqlite3"
   $env:MEMORA_USER_ID = "demo-user"
   $env:MEMORA_LOCAL_TOKEN = [Convert]::ToHexString(
     [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
   ).ToLowerInvariant()
   ```

   `MEMORA_LOCAL_TOKEN` is a dedicated random credential for the local Memora API. It is not an OpenAI key or ChatGPT credential. Keep this terminal open and copy the generated value into the extension popup; never commit or log it.

4. Start the local API on the standard MVP port:

   ```powershell
   python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765
   ```

5. In another terminal, verify it:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8765/health
   ```

For offline development, set `MEMORA_EMBEDDING_PROVIDER=local`; no API key is needed. Do not mix indexes created by different embedding providers or models.

### Extension

1. Build and verify the extension:

   ```powershell
   Set-Location extension
   npm install
   npm run test
   npm run typecheck
   npm run build
   ```

2. Open `chrome://extensions`, enable Developer mode, select **Load unpacked**, and choose `extension/dist`.
3. After every rebuild, click **Reload** for Memora and refresh the ChatGPT tab.

The manifest permits only `http://127.0.0.1/*` and `http://localhost/*`, while runtime settings further restrict the backend to port `8765`. The extension stores the Memora token in `chrome.storage.local` and contains no OpenAI credential.

## Usage

1. Start the backend on `http://127.0.0.1:8765`.
2. Open the Memora popup, keep the default URL, paste the same `MEMORA_LOCAL_TOKEN`, and save.
3. Import ChatGPT history from an explicitly selected JSON/ZIP file, or index the safe demo samples:

   ```powershell
   python -m scripts.demo_rag "Where was I running my model again?" --database .\memora.sqlite3
   ```

   The command indexes all five synthetic sample conversations and prints rankings and context. Use the same embedding provider as the running backend.

4. Open ChatGPT and type `Where was I running my model again?` without submitting.
5. Click **Retrieve Memory** and confirm **Drone Detection Project** is the top match.
6. Click **Use This Context**, review the updated draft, and submit it manually.

To upload a real ChatGPT export, use the extension popup. Supported inputs are `conversations.json`, numbered conversation JSON files, or a ZIP containing them. Never copy a real export into this repository.

## Privacy

- Selected conversation exports are sent to the user's local Memora backend.
- API keys remain server-side and are never included in extension code.
- Sensitive endpoints require the dedicated local Memora bearer token; database scope comes from server-side `MEMORA_USER_ID`.
- Retrieval and context insertion each require an explicit user action.
- Memora never automatically submits a ChatGPT message.
- Raw imports, message text, context, embeddings, and secrets are not logged by default.
- Real exports, local databases, `.env`, and extension build artifacts are ignored by Git.

Memora does not currently implement end-to-end encryption.

## Current MVP Limitations

- A local backend is required.
- The local bearer token is a single-user demo boundary, not production multi-user authentication.
- ChatGPT integration relies on non-public DOM selectors that may change.
- SQLite performs linear vector search and is intended for demo-scale data.
- Imports are synchronous and can take several minutes with OpenAI embeddings.
- ChatGPT export schemas may change.
- Only the ChatGPT adapter is implemented.
- Structured durable-memory extraction is modeled but not part of the active retrieval pipeline.

## Conversation JSON Format

The direct import endpoint accepts one conversation with a required ID and non-empty messages. Roles are `user`, `assistant`, `system`, or `tool`; timestamps are optional timezone-aware ISO 8601 values.

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

Sensitive API calls require `Authorization: Bearer <MEMORA_LOCAL_TOKEN>`. The caller cannot select the database user scope. Retrieval queries are limited to 2,000 characters, `top_k` to 1–10, and history imports to 10 selected files. In-process limits allow 60 retrievals per minute and 10 imports per 10 minutes by default. These controls protect the local demo but are not distributed production rate limiting.

The current MVP is designed for local single-user use. Bind it only to `127.0.0.1`; do not expose it directly to a LAN or the public internet.

## Tests

Normal automated tests use deterministic local embeddings and do not call OpenAI:

```powershell
python -m unittest discover -s tests -v
python -m compileall backend scripts tests
Set-Location extension
npm run test
npm run typecheck
npm run build
```

## Tech Stack

- Python 3.11+, FastAPI, Pydantic, Uvicorn
- SQLite
- OpenAI Python SDK (`text-embedding-3-small`)
- TypeScript, Chrome Manifest V3, esbuild, Vitest

## Built With Codex

Codex was the primary engineering agent used to scaffold, implement, test, debug, and iterate on Memora during the OpenAI hackathon. Product decisions and demo validation remained under human direction.

## Demo Resources

- [2–3 minute demo script](docs/demo-script.md)
- [Fresh-start checklist](docs/fresh-start-checklist.md)
- [Architecture](docs/architecture.md)
