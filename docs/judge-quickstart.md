# Memora Judge Quickstart

This guide uses Windows PowerShell and the repository's existing synthetic demo data.

## Requirements

- Python 3.11+
- Node.js 20+ and npm
- Google Chrome
- An OpenAI API key with API access and available quota

## 1. Clone

```powershell
git clone https://github.com/suheil2004/Memora.git
cd Memora
```

## 2. Python Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## 3. Configure Environment

Set these values in the terminal used for indexing and running the backend. Never commit the key.

```powershell
$env:OPENAI_API_KEY = "YOUR_PRIVATE_KEY"
$env:MEMORA_EMBEDDING_PROVIDER = "openai"
$env:OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
$env:MEMORA_DATABASE_URL = "sqlite:///./memora.sqlite3"
$env:MEMORA_USER_ID = "demo-user"
$env:MEMORA_LOCAL_TOKEN = [Convert]::ToHexString(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLowerInvariant()
```

Keep this shell open. The generated Memora token is separate from the OpenAI key. Copy it into the extension popup without committing or showing it.

## 4. Load Demo Memory

Run the existing demo script from the repository root. Supplying `--database` keeps the five synthetic conversations in the same database the backend will open. They are indexed under `demo-user`.

```powershell
python -m scripts.demo_rag "Where was I running my model again?" --database .\memora.sqlite3
```

Expected: **Drone Detection Project** ranks first and the generated context mentions Raspberry Pi 4 camera streaming and Windows CUDA inference.

## 5. Start Backend

```powershell
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765
```

Keep this terminal running.

## 6. Verify Backend

Open `http://127.0.0.1:8765/health`, or run in another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Expected JSON:

```json
{
  "status": "ok",
  "service": "memora"
}
```

## 7. Build Extension

From the repository root:

```powershell
cd extension
npm install
npm run test
npm run typecheck
npm run build
cd ..
```

## 8. Load Extension

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select the repository's `extension/dist` directory.
5. After any rebuild, click **Reload** for Memora and refresh the ChatGPT tab.

## 9. Configure Memora

Open the Memora toolbar popup and save:

- Backend URL: `http://127.0.0.1:8765`
- Local authentication token: the current shell's `MEMORA_LOCAL_TOKEN`

Confirm the popup reports **Connected**.

## 10. Run Core Demo

1. Open a fresh conversation at `https://chatgpt.com/`.
2. Type, but do not submit: `Where was I running my model again?`
3. Click **Retrieve Memory**.
4. Confirm **Drone Detection Project** appears with the Raspberry Pi / Windows CUDA context.
5. Click **Use This Context** and confirm the draft changes.
6. Review the inserted context and submit manually.

Memora never submits automatically.

## Troubleshooting

**Backend Offline:** Confirm Uvicorn is still running on port `8765`, then open the popup and save the backend URL again.

**Extension changed:** Reload Memora in `chrome://extensions` and refresh the ChatGPT tab.

**OpenAI quota or key error:** Confirm the private key has API access, billing/quota is available, and the variables were set in the current backend shell.

**No memory:** Re-run the demo command from the repository root and confirm the backend uses `MEMORA_USER_ID=demo-user` and `memora.sqlite3`.

**Embedding mismatch:** Remove the disposable demo database or use a new database path, then re-index with the same provider and model configured for the backend. Do not mix local and OpenAI vectors.

## Important MVP Notes

- A local backend is required.
- The local bearer token is not production multi-user authentication.
- Bind Memora only to `127.0.0.1`; do not expose this MVP to a LAN or public network.
- ChatGPT integration depends on DOM selectors that may change.
