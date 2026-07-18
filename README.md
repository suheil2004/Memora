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

## Run the HTTP API

Install the project dependencies as shown above, select an embedding provider, and start FastAPI locally:

```powershell
$env:MEMORA_EMBEDDING_PROVIDER = "local"
$env:MEMORA_DATABASE_URL = "sqlite:///./memora.sqlite3"
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000 --reload
```

OpenAI semantic mode uses the same API and pipeline:

```powershell
$env:MEMORA_EMBEDDING_PROVIDER = "openai"
$env:OPENAI_API_KEY = "your-api-key"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Check health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Import and index the drone sample:

```powershell
$conversation = Get-Content .\samples\drone_detection.json -Raw | ConvertFrom-Json
$conversation | Add-Member -NotePropertyName user_id -NotePropertyValue "demo-user"
$importBody = $conversation | ConvertTo-Json -Depth 10
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/conversations/import `
  -ContentType "application/json" `
  -Body $importBody
```

Retrieve compact context:

```powershell
$queryBody = @{
  user_id = "demo-user"
  query = "Where was I running the neural network again?"
  top_k = 5
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/context/retrieve `
  -ContentType "application/json" `
  -Body $queryBody
```

`user_id` is an explicit request field only for the hackathon MVP. It is not authentication and must be replaced before production use. CORS defaults to local development origins only. Set `MEMORA_CORS_ORIGINS` to a comma-separated allowlist, including the exact `chrome-extension://...` origin once an unpacked extension ID is stable; never use `*` in production.

## Build and load the Chrome extension

Requirements: Node.js 20+ with npm. The extension communicates only with a locally permitted Memora backend; it contains no OpenAI credential or RAG implementation.

```powershell
Set-Location extension
npm install
npm run test
npm run typecheck
npm run build
```

Then open Chrome → Extensions → enable Developer mode → Load unpacked → select `extension/dist`. Click the Memora toolbar icon to configure the backend URL and temporary demo user ID. The manifest permits only `127.0.0.1` and `localhost` HTTP backends; other hosts require an explicit manifest permission change and rebuild.

After loading or updating the extension, open its toolbar popup and click **Save** once while the backend is running. The popup performs a foreground `/health` check. On Chrome versions using Local Network Access permissions, this is where Chrome can ask you to allow access to the local backend; a background service worker cannot display that prompt by itself. Then reload the extension from `chrome://extensions` and retry retrieval if its files were rebuilt.

The backend CORS allowlist can include the extension origin once Chrome assigns a stable ID:

```powershell
$env:MEMORA_CORS_ORIGINS = "http://localhost:3000,chrome-extension://YOUR_EXTENSION_ID"
```

### Manual hackathon demo

1. Start the backend with OpenAI embeddings:

   ```powershell
   $env:MEMORA_EMBEDDING_PROVIDER = "openai"
   $env:OPENAI_API_KEY = "your-api-key"
   $env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
   $env:MEMORA_DATABASE_URL = "sqlite:///./memora.sqlite3"
   python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765
   ```

2. Import `samples/drone_detection.json` using the API commands above with `user_id` set to `demo-user`.
3. Build and load `extension/dist` as an unpacked extension.
4. Open `https://chatgpt.com/` and type, but do not submit: `Where was I running the neural network again?`
5. Click **Retrieve memory** in the Memora panel.
6. Confirm that the panel shows **Drone Detection Project**, its relevance score, and the Raspberry Pi/CUDA context.
7. Click **Use this context** and confirm the compact context appears before the original ChatGPT question.
8. Review the updated draft; ChatGPT does not submit it automatically.

Retrieval and insertion each require separate explicit clicks. The extension never submits the draft or captures the current conversation. If the draft changes after retrieval, Memora refuses insertion to protect the user's edits.

### ChatGPT adapter selectors

The adapter tries these selectors in order:

```text
#prompt-textarea
textarea[data-id="root"]
main form [contenteditable="true"][data-virtualkeyboard="true"]
main form [contenteditable="true"]
```

ChatGPT's DOM is not a public stable API, so these selectors may require maintenance. All such assumptions are isolated in `extension/src/adapters/chatgpt-adapter.ts`.

## Import ChatGPT conversation history

Memora imports files supplied explicitly by the user; it does not use a private or unsupported ChatGPT history API. Supported MVP inputs are:

- A `conversations.json` containing an array of conversations.
- Individual JSON files containing one conversation, an array, or a top-level `conversations` array.
- Numbered files named like `conversations-1.json`, `conversations_001.json`, or `1.json`, selected together.
- A ZIP containing those conversation JSON names. ZIP entries are inspected in memory and never extracted.

The importer supports the synthetic graph shape represented by a `mapping` plus `current_node`, and a simpler flat `messages` list. For graphs, it walks from `current_node` through parents to reconstruct the active branch. If `current_node` is unavailable, it chooses the latest leaf it can identify. Only user/assistant textual parts are indexed; unsupported media and internal/system nodes are skipped. Export formats can evolve, so compatibility with every historical ChatGPT export variant is not claimed.

### API import

Start the backend and upload one or more files:

```powershell
$files = Get-Item .\path\to\conversations.json
$response = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8765/api/v1/import/chatgpt `
  -Form @{ user_id = "demo-user"; files = $files }
$response | ConvertTo-Json -Depth 5
```

Alternatively use curl:

```powershell
curl.exe -X POST http://127.0.0.1:8765/api/v1/import/chatgpt `
  -F "user_id=demo-user" `
  -F "files=@C:\path\to\conversations.json;type=application/json"
```

The synchronous response reports conversations found/imported/skipped, messages, chunks, provider/model, elapsed time, and sanitized errors. Large OpenAI imports can take several minutes. Chunks from each conversation are embedded as a batch; this MVP does not have a background queue or cross-conversation mega-batch.

### Extension import

Reload the unpacked extension after building, open its toolbar popup, choose one or more JSON files or one ZIP, and click **Import ChatGPT History**. Browser file access occurs only after that explicit selection. The export goes to the local Memora backend; it is parsed and chunked locally. Only chunk text required for embeddings is sent by the backend to the configured embedding provider. The browser never receives or stores an OpenAI API key.

### Duplicate behavior

Memora stores a normalized SHA-256 fingerprint for each user-scoped conversation ID. An unchanged re-import is skipped without recomputing embeddings. A changed conversation with the same ID replaces and re-indexes the prior copy. Conversation IDs and fingerprints are scoped by the explicit MVP `user_id`.

### Manual real-export test

1. Request and download your official ChatGPT data export.
2. Do not copy the real export into this repository.
3. Start Memora with `MEMORA_EMBEDDING_PROVIDER=openai` and the backend on port `8765`.
4. Open the Memora extension popup and confirm `demo-user`.
5. Select the export's `conversations.json`, numbered JSON files, or ZIP and click **Import ChatGPT History**.
6. Record the reported conversation/message/chunk counts and duration.
7. Open a fresh ChatGPT conversation and type a vague question about a genuinely old discussion.
8. Click **Retrieve memory** and confirm the correct historical conversation appears.
9. Click **Use this context**, review the inserted context, and submit manually if desired.

Real exports, `conversations.json`, and ChatGPT export ZIPs are ignored by Git. Synthetic fixtures under `tests/fixtures` are explicitly allowed. The backend does not log conversation bodies, does not expose embeddings, closes uploads, and never extracts ZIP contents. Limits currently include 1,000 ZIP entries, 200 MiB total uncompressed ZIP content, 50 MiB per JSON file, and 250 MiB per multipart request.

## Current status and limitations

The core models distinguish original searchable conversation chunks from extracted durable memories. Python `Protocol` contracts keep providers and retrieval logic independent. The local hashes provide reproducible lexical similarity, while OpenAI embeddings support semantic retrieval. SQLite still performs an in-process linear scan, suitable only for the hackathon-scale demo. The extension remains an untouched shell with no DOM behavior.
