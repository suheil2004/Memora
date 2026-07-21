# Setting Up Memora

Memora is currently a Windows-first, developer-operated hackathon MVP. The launcher prepares the repository and runs the local backend; Chrome requires one manual unpacked-extension installation.

## Prerequisites

- Windows with Windows PowerShell 5.1 or newer PowerShell
- Python 3.11 or newer
- Node.js 20 or newer with npm
- Google Chrome
- An OpenAI API key only for Enhanced mode

The launcher validates but does not install system runtimes or Chrome.

## Clone and launch

Open PowerShell in the repository root and run:

```powershell
.\start-memora.ps1
```

On first run, the launcher:

1. Finds and validates Python, Node.js, and npm, including paths containing spaces.
2. Creates `.venv` when absent or repairs missing/inconsistent Python dependencies with `python -m pip install -e .`.
3. Installs locked extension dependencies when needed.
4. Prompts for **Enhanced** or **Local** mode when no provider configuration exists.
5. Creates and persists a stable local authentication token if one does not exist.
6. Builds `extension/dist` when required and verifies all production files.
7. Starts FastAPI on `http://127.0.0.1:8765`.
8. Verifies readiness through authenticated memory statistics.

Keep the launcher window open. Press Ctrl+C or close it to stop the backend.

### Launcher options

```powershell
.\start-memora.ps1 -Setup             # review/change processing mode, then exit after setup
.\start-memora.ps1 -RebuildExtension  # force a production extension rebuild
.\start-memora.ps1 -ShowToken         # deliberately display the local token
.\start-memora.ps1 -Verbose           # show bounded diagnostics
```

Normal launches reuse the existing `.venv`, provider configuration, database URL, API key, relevance threshold, and valid token. They do not rotate or overwrite them.

## Choose a processing mode

### Enhanced mode

Enhanced mode configures OpenAI semantic embeddings, OpenAI MemoryFact extraction, and OpenAI MemoryBrief synthesis, each with deterministic fallback where implemented. It is the recommended full demo experience and requires an OpenAI API key.

If no key is configured, the launcher requests it through a hidden prompt. Saving it to the gitignored plaintext `.env` is explicit and optional; otherwise it applies only to that launch.

OpenAI embeddings require a calibrated `MEMORA_RELEVANCE_MIN_SIMILARITY`. The launcher validates and may save the value but does not choose one. The diagnostic calibration utility is:

```powershell
.\.venv\Scripts\python.exe -m scripts.calibrate_relevance
```

Calibration and live OpenAI use can consume provider quota. Do not run them unless intended.

### Local mode

Local mode uses deterministic feature-hash embeddings, deterministic MemoryFacts, and deterministic MemoryBriefs. It requires no API key and is intended for offline development, tests, and zero-cost evaluation. Its retrieval and synthesis quality may differ from Enhanced mode.

Changing embedding provider or model requires a compatible database or deliberate re-indexing. The launcher warns before changing mode against a populated SQLite database and never deletes or rewrites it automatically.

## Install the Chrome extension

After the launcher has built the extension:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose `<repository>\extension\dist`.
5. Open the Memora toolbar popup.
6. Keep the backend URL as `http://127.0.0.1:8765`.
7. Paste the local authentication token copied on first generation and select **Save settings**.
8. Confirm **Ready** or **No memory imported yet**.

The Memora token is not the OpenAI API key. It authorizes the local extension-to-backend API only.

After any extension rebuild, select **Reload** for Memora in `chrome://extensions` and refresh the ChatGPT tab. Chrome does not automatically load new files from `extension/dist` into an already running extension instance.

## Import memory

### ChatGPT history

1. Export your ChatGPT data through ChatGPT's supported export process.
2. Open the Memora popup.
3. Under **Import memory**, select the supported JSON or ZIP export files.
4. Select **Import history** and wait for the local import summary.

Memora does not access the ChatGPT account automatically. ZIPs are inspected in memory rather than extracted. Compatible exports may recover attachment metadata and safely resolvable text PDFs; ambiguous or missing assets remain metadata-only.

### Additional PDFs

Use **Import additional PDFs** for up to the configured file limit of text-based PDF files. Memora extracts text locally, indexes bounded page chunks, and preserves filename/page provenance. OCR, scanned/image-only PDFs, and encrypted PDFs are not supported.

## Use Memora

1. Open `https://chatgpt.com/` and start a fresh conversation.
2. Write a question without submitting it.
3. Open the Memora panel and select **Retrieve memory**.
4. Review the MemoryBrief cards, timestamps, and sources.
5. Use **Best match** or **Most recent** as needed.
6. For another draft, use **Search current prompt**; it reads the composer at click time and replaces the visible results.
7. **Clear results** removes only panel results and makes no deletion request.
8. Select **Use This Context** for one brief, review the resulting draft, and submit manually.

If the draft changes between retrieval and insertion, Memora refuses insertion and asks for another retrieval.

## Privacy & Memory

The popup shows authenticated aggregate counts for conversations, attachments, searchable documents, conversation chunks, and document chunks.

**Clear Memora data** requires confirmation and deletes the configured user's records from the active SQLite database. It does not delete source exports, copied databases, backups, provider-held data, or text already inserted into ChatGPT.

## Future runs and stopping

Start Memora from the repository root each time:

```powershell
.\start-memora.ps1
```

If an authenticated matching backend is already running, the launcher reports it rather than starting another process. It refuses to kill a process using port 8765.

For a backend started by the launcher, press Ctrl+C or close the launcher window to stop it.

## Test the installation

The automated suites use local or mocked providers and do not call OpenAI:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall backend scripts tests

Set-Location extension
npm run test
npm run typecheck
npm run build
Set-Location ..

& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\test_start_memora_launcher.ps1
```

## Troubleshooting

### Python or Node.js is not found

Run `python --version`, `node --version`, and `npm.cmd --version` directly. Ensure supported executables are on `PATH`, then reopen PowerShell. The launcher distinguishes missing executables, invocation failures, malformed versions, and unsupported versions.

### `.venv` exists but dependencies are missing

Run the launcher again. It validates Memora distribution metadata and required runtime imports, then repairs an incomplete environment automatically. Use `-Verbose` for bounded stage diagnostics.

### Extension build fails

Run with `-Verbose`. npm commands execute from `extension/`, and a successful build must contain `background.js`, `content.js`, `popup.js`, `popup.html`, `popup.css`, and `manifest.json` in `extension/dist`.

### Backend is offline

Run `.\start-memora.ps1` from the repository root and keep its window open. Confirm port 8765 is not occupied by an unrelated process.

### Authentication failed

The popup token does not match the backend's stable `MEMORA_LOCAL_TOKEN`. When it is safe to display the credential, run `.\start-memora.ps1 -ShowToken`, paste that exact token into the popup, and save.

### Wrong or incompatible database

Check `MEMORA_DATABASE_URL` and the active provider/model. Memora rejects vectors created in an incompatible embedding space. It does not migrate, clear, or re-index a populated database automatically.

### Configuration unavailable

Check the selected provider names, OpenAI key for Enhanced mode, calibrated relevance threshold, database URL, and embedding compatibility. Authenticated readiness does not itself invoke embeddings or synthesis.

### Extension changes do not appear

Run `.\start-memora.ps1 -RebuildExtension`, reload Memora in `chrome://extensions`, and refresh ChatGPT. Confirm Chrome is loading `extension/dist`, not the source directory.

## Manual developer startup

The launcher is the supported project path. Advanced users may start components manually, but must provide the same environment variables and must keep the backend bound to loopback. Never expose this MVP using `0.0.0.0` or place provider credentials in extension code.
