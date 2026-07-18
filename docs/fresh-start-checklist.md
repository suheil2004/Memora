# Fresh-Start Demo Checklist

Use this from a clean checkout before demo day.

- [ ] Clone the repository and open its root.
- [ ] Confirm Python 3.11+, Node.js 20+, npm, and Chrome are installed.
- [ ] Create and activate `.venv`: `python -m venv .venv`; `.\.venv\Scripts\Activate.ps1`.
- [ ] Install Python dependencies: `python -m pip install -e .`.
- [ ] Run backend tests: `python -m unittest discover -s tests -v`.
- [ ] Compile Python: `python -m compileall backend scripts tests`.
- [ ] Set `OPENAI_API_KEY`, `MEMORA_EMBEDDING_PROVIDER=openai`, `OPENAI_EMBEDDING_MODEL=text-embedding-3-small`, and `MEMORA_DATABASE_URL=sqlite:///./memora.sqlite3` in the shell.
- [ ] Index and verify demo data: `python -m scripts.demo_rag "Where was I running my model again?" --database .\memora.sqlite3`.
- [ ] Start the API: `python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8765`.
- [ ] Confirm `Invoke-RestMethod http://127.0.0.1:8765/health` returns Memora status `ok`.
- [ ] In `extension`, run `npm install`, `npm run test`, `npm run typecheck`, and `npm run build`.
- [ ] Confirm `extension/dist` contains `manifest.json`, `background.js`, `content.js`, `popup.js`, `popup.html`, and `popup.css`.
- [ ] In `chrome://extensions`, enable Developer mode and load `extension/dist` unpacked.
- [ ] Open the popup, keep `http://127.0.0.1:8765`, set `demo-user`, save, and confirm **Connected**.
- [ ] Open ChatGPT and refresh the tab after loading/reloading the extension.
- [ ] Type `Where was I running my model again?` without submitting.
- [ ] Click **Retrieve Memory** and verify **Drone Detection Project** appears with Raspberry Pi / Windows CUDA context.
- [ ] Click **Use This Context**, verify the draft is updated, then submit manually.
- [ ] Optionally select a safe synthetic ChatGPT fixture in the popup to verify history import.
- [ ] Keep real exports, `.env`, API keys, and `memora.sqlite3` out of commits and screen sharing.

