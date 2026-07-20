# Memora Judge Quickstart

This Windows PowerShell guide separates the presenter-ready path from a full clean local setup. Memora is a developer-operated hackathon MVP, not a consumer installer.

## A. Fast prepared demo

Assumptions:

- The repository is cloned and Python dependencies are installed.
- The presenter has prepared a private local demo database using synthetic or sanitized data; it is never committed.
- `extension/dist` is already built and loaded unpacked in Chrome.
- A supported embedding/synthesis provider and private API key are configured in the backend shell.
- The same dedicated `MEMORA_LOCAL_TOKEN` is configured in the backend and extension popup.

### 1. Start the backend

From the repository root, with the prepared environment still configured:

```powershell
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765
```

Open the extension popup. Expected: **Ready**. Other states are actionable:

- **No memory imported yet** — the configured user/database is empty.
- **Authentication failed** — the extension token does not match `MEMORA_LOCAL_TOKEN`.
- **Memora is offline** — the local service cannot be reached.
- **Configuration unavailable** — check backend provider configuration.

Readiness uses an authenticated aggregate-statistics request and does not trigger provider-backed retrieval.

### 2. Run the primary flow

1. Open a fresh conversation at `https://chatgpt.com/`.
2. Type a rehearsed question about a project with original and current versions; do not submit.
3. Click **Retrieve Memory**.
4. Confirm the current-state MemoryBrief appears first and historical related memory remains separate.
5. Expand **Sources**; show a recovered PDF/page source only if it exists in the prepared fixture.
6. Toggle **Best match / Most recent**.
7. Click **Use This Context** and inspect the bounded selected brief in the composer.
8. Submit manually or stop before submission. Memora never presses Send.

Retrieval loading messages change at fixed elapsed times to reassure the user; they are not streaming backend progress.

### 3. Reliable fallback

Use the repository's synthetic drone fixture and ask:

> Where was I running my model again?

Expected: **Drone Detection Project**, Raspberry Pi 4 camera streaming, and Windows laptop CUDA inference.

## B. Full local setup

### Requirements

- Python 3.11+
- Node.js 20+ and npm
- Google Chrome
- A supported provider configuration; the semantic demo uses an OpenAI API key with quota

### 1. Clone and install

```powershell
git clone https://github.com/suheil2004/Memora.git
Set-Location Memora
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### 2. Configure one backend shell

```powershell
$env:OPENAI_API_KEY = "YOUR_PRIVATE_KEY"
$env:MEMORA_EMBEDDING_PROVIDER = "openai"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
$env:MEMORA_SYNTHESIS_PROVIDER = "openai"
$env:MEMORA_SYNTHESIS_MODEL = "gpt-5.6-luna"
$env:MEMORA_DATABASE_URL = "sqlite:///./memora.sqlite3"
$env:MEMORA_USER_ID = "demo-user"
$env:MEMORA_LOCAL_TOKEN = [Convert]::ToHexString(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLowerInvariant()
```

Keep the shell open. The Memora token is separate from the OpenAI key. Never commit, record, or show either credential.

### 3. Prepare synthetic demo memory

```powershell
python -m scripts.demo_rag "Where was I running my model again?" --database .\memora.sqlite3
```

Expected: **Drone Detection Project** ranks first and context mentions Raspberry Pi 4 streaming plus Windows CUDA inference. Use the same embedding provider/model for indexing and the backend; incompatible vector identities are rejected.

### 4. Start and verify the backend

```powershell
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765
```

Public liveness is available at `http://127.0.0.1:8765/health`, but the extension popup's authenticated readiness state is the meaningful demo check.

### 5. Build and load the extension

In another terminal:

```powershell
Set-Location extension
npm install
npm run test
npm run typecheck
npm run build
```

1. Open `chrome://extensions` and enable **Developer mode**.
2. Choose **Load unpacked** and select `extension/dist`.
3. After every rebuild, click **Reload** for Memora and refresh the ChatGPT tab.
4. In the popup, use `http://127.0.0.1:8765`, paste the same local token, and save.
5. Confirm **Ready**, then run the flow above.

## Repository inspection without private history

Judges do not need a presenter database, personal ChatGPT export, or live provider call to inspect and test the project:

```powershell
python -m unittest discover -s tests -v
python -m compileall backend scripts tests
Set-Location extension
npm run test
npm run typecheck
npm run build
```

Automated tests use deterministic local or mocked providers. Current verified totals are **101/101 backend** and **72/72 extension**.

## Optional history and PDF import

The popup accepts explicitly selected supported ChatGPT JSON/ZIP exports. Compatible exports may reconnect attachment metadata with safely resolvable text PDFs and preserve page provenance. Missing or ambiguous binaries remain metadata-only; scanned/image-only PDFs and OCR are unsupported. **Import additional PDFs** is an optional fallback.

For a large extracted export, use `python -m scripts.import_chatgpt_export "<export-directory>"` with the same database, user, and embedding configuration. Never copy private exports or databases into the repository.

## Privacy & Memory demonstration

The popup shows authenticated aggregate counts. **Clear Memora data** requires confirmation; **Cancel** is non-destructive. Explicit deletion clears active database records and open memory-card state. It does not delete manual backups, source exports, credentials, or text already inserted into ChatGPT. Use only a disposable demo database when demonstrating deletion.

## Troubleshooting

- **Offline:** confirm Uvicorn is running on `127.0.0.1:8765`.
- **Authentication failed:** copy the exact current shell's `MEMORA_LOCAL_TOKEN` into the popup.
- **No memory imported:** verify `MEMORA_USER_ID`, database URL, and prepared data.
- **Configuration unavailable/provider failure:** verify the backend shell's provider model, API access, and quota.
- **Embedding mismatch:** use a new disposable database or re-index with the same provider/model. Do not mix vector spaces.
- **Extension changed:** reload it in `chrome://extensions` and refresh ChatGPT.

## Honest MVP boundaries

The backend must run locally and remain bound to loopback. The bearer token is not production multi-user identity, SQLite search is linear, the database has no encrypted-at-rest guarantee, query-time fact/synthesis calls add latency, ChatGPT DOM selectors may change, prompt-injection risk cannot be eliminated, and not every attachment can be recovered. Production packaging and identity are roadmap work.
