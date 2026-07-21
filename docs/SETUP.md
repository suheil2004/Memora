# Setting Up Memora

Memora is a Windows-oriented, developer-operated hackathon MVP. The launcher prepares the local project and starts the backend; Chrome still requires one manual unpacked-extension installation.

## Fast setup

### Prerequisites

- Windows with Windows PowerShell 5.1 or newer PowerShell
- Python 3.11 or newer
- Node.js 20 or newer with npm
- Google Chrome
- An OpenAI API key only when an OpenAI embedding, MemoryFact, or synthesis provider is selected

The launcher does not install system software, Chrome, Python, or Node.js.

### First run

1. Clone or download Memora and open PowerShell in the repository root.
2. Run:

   ```powershell
   .\start-memora.ps1
   ```

3. The launcher checks Python, Node, and npm; creates `.venv` if needed; and installs project-local Python and locked extension dependencies when missing.
4. On first setup without provider configuration, choose a processing mode. Pressing Enter selects **Enhanced**.
5. The launcher generates a stable Memora token, builds `extension/dist`, starts FastAPI on `127.0.0.1:8765`, and verifies authenticated readiness.
6. On first token generation, it stores the token in the gitignored `.env` and copies it to the clipboard without printing it.
7. Keep the launcher window open. Closing it or pressing Ctrl+C stops the local backend.

## Choose a processing mode

### Enhanced — Recommended

This is the recommended full Memora experience. It uses the existing OpenAI pipeline for semantic embeddings, query-time MemoryFact extraction, and MemoryBrief synthesis. It requires an OpenAI API key and is intended to provide the best Memora quality.

If `OPENAI_API_KEY` is absent, enter it at the hidden prompt. Saving is opt-in: the launcher explains that `.env` is local plaintext excluded from Git and defaults to using the key only for the current launch. The key is never printed or copied to the clipboard.

OpenAI semantic embeddings also require an explicitly measured `MEMORA_RELEVANCE_MIN_SIMILARITY`. The repository does not claim a universal threshold. Enter a value calibrated for the intended compatible index or stop and use `scripts.calibrate_relevance` for diagnostic guidance. The launcher validates and persists the non-secret threshold but never invents one.

### Local

Local mode uses local feature-hash embeddings plus deterministic MemoryFacts and MemoryBriefs. No OpenAI API key is needed. It is useful for offline testing, development, and zero-cost evaluation; retrieval and summaries may differ from Enhanced mode.

The selected provider configuration persists in `.env`. Normal launches display the active mode and do not prompt again.

## Install the Chrome extension once

The hackathon MVP is not distributed through the Chrome Web Store:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose the repository's `extension/dist` directory.
5. Open the Memora toolbar popup.
6. Keep `http://127.0.0.1:8765` as the backend URL.
7. Paste the Memora token copied by the launcher and save.
8. Confirm the popup reports **Ready** or **No memory imported yet**.

After rebuilding extension source, click **Reload** for Memora and refresh the ChatGPT tab.

## Import ChatGPT history

Use the popup to select a supported ChatGPT JSON/ZIP export. Memora does not automatically access the account. Compatible exports can conservatively reconnect historical attachment metadata and safely resolvable text PDFs; ambiguous assets remain metadata-only.

For a very large already-extracted export, stop the backend and use the local incremental CLI with the same `.env` configuration:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_chatgpt_export "<export-directory>"
```

Do not place private exports or databases in the repository.

## Daily use

After initial setup:

1. Run `.\start-memora.ps1`.
2. Open ChatGPT.
3. Use the Memora panel.

The persisted token is reused; it does not need to be regenerated or pasted every session. If Memora is already running with the configured token, the launcher reports that state instead of starting a duplicate process.

## Launcher flags

| Flag | Behavior |
| --- | --- |
| `-Setup` | Review or change processing mode, prepare configuration/dependencies/build, then exit without starting FastAPI. |
| `-RebuildExtension` | Force a production extension rebuild. |
| `-ShowToken` | Intentionally display the configured Memora token for manual recovery. Avoid screen sharing or logging this output. |
| `-Verbose` | Show additional command/diagnostic information when setup or startup fails. Secrets are still not intentionally printed. |

Examples:

```powershell
.\start-memora.ps1 -Setup
.\start-memora.ps1 -RebuildExtension
.\start-memora.ps1 -ShowToken
```

## Local configuration

The backend does not load `.env` itself. The launcher parses the root `.env` as data and exports only supported `KEY=VALUE` entries to its backend child process. Blank lines and `#` comment lines are allowed; PowerShell expressions are never executed. Existing process environment values take precedence. Valid existing provider/model/key/threshold configuration is respected without prompting or overwriting it during normal startup.

`.env` and `.env.*` are gitignored except for the placeholder-only `.env.example`. The launcher preserves existing values and does not overwrite a configured database or rotate a valid token. Non-provider defaults include:

```dotenv
MEMORA_DATABASE_URL=sqlite:///./memora.sqlite3
MEMORA_USER_ID=demo-user
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
MEMORA_SYNTHESIS_MODEL=gpt-5.6-luna
```

Enhanced writes `openai` to the existing embedding, synthesis, and fact provider variables. Local writes `local`, `deterministic`, and `deterministic`. The client never selects `MEMORA_USER_ID`; scope remains server-derived.

### Changing mode safely

Run `.\start-memora.ps1 -Setup`. The launcher shows the current mode and keeps it by default. If a requested change switches embedding providers while the configured database file contains data, Memora warns that compatible re-indexing is required and defaults to cancelling the switch. Explicit confirmation changes configuration only: it never edits or deletes the database, embeddings, conversations, documents, token, or source history. Existing backend provider/model/dimension checks still reject incompatible vectors. Use a new database or deliberately re-index user-supplied history before retrieval in the new embedding space.

## Readiness states

- **Ready:** authenticated backend is running and memory exists.
- **No memory imported yet:** backend and token work; import history through the popup.
- **Authentication failed:** the popup token does not match the stable `MEMORA_LOCAL_TOKEN` in `.env` or the launch environment.
- **Memora is offline:** run the launcher and keep its window open.
- **Configuration unavailable:** review provider names, API-key availability, semantic relevance threshold, database URL, and embedding compatibility.

The launcher and popup use authenticated `GET /api/v1/memory/stats`. This does not call retrieval, embeddings, MemoryFact extraction, or synthesis.

## Troubleshooting

### Python, Node, or npm is missing

Install the required supported runtime, reopen PowerShell so it is on `PATH`, and run the launcher again. The launcher never installs system runtimes.

### Port 8765 is already in use

If the authenticated Memora instance matches, the launcher reports it as already running. If another Memora token or another process owns the port, stop or reconfigure that process. The launcher never kills an unrelated process.

### Extension does not appear

Confirm `extension/dist` is loaded—not the `extension` source directory. After a rebuild, reload Memora in `chrome://extensions` and refresh ChatGPT.

### Token mismatch

Run `.\start-memora.ps1 -ShowToken` only when it is safe to display the token, then paste that exact value into the popup. Normal launches never print it.

### OpenAI key is missing

Enhanced or another OpenAI-backed configuration prompts with hidden input. Saving is optional and explicit. A saved key is plaintext in the local gitignored `.env`; it is never copied to the clipboard. Local mode never asks for one.

### Backend closes

The backend intentionally belongs to the launcher session. Keep the launcher open; it does not install a background service.

### Readiness times out

Run with `-Verbose`, verify provider and database configuration, and confirm local security software is not blocking loopback. The startup wait is bounded to 30 seconds.

## Manual developer setup

Advanced users can bypass the launcher:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .

$env:MEMORA_DATABASE_URL = "sqlite:///./memora.sqlite3"
$env:MEMORA_USER_ID = "demo-user"
$env:MEMORA_EMBEDDING_PROVIDER = "local"
$env:MEMORA_SYNTHESIS_PROVIDER = "deterministic"
$env:MEMORA_FACT_PROVIDER = "deterministic"
$env:MEMORA_LOCAL_TOKEN = [Convert]::ToHexString(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLowerInvariant()

Set-Location extension
npm ci
npm run build
Set-Location ..

.\.venv\Scripts\python.exe -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765
```

Manual shell variables are not persisted automatically. Never bind this MVP to `0.0.0.0`, expose it to a LAN/public network, or place credentials in extension code.
