# Memora Demo Video Script

Target duration: 2–3 minutes.

## 0:00–0:15 — Hook

**On screen:** A fresh ChatGPT conversation and the Memora panel.

**Narration:** “AI is powerful, but every new conversation can feel like starting over. Memora is a personalized memory layer that brings relevant context from your previous conversations into the AI chat you already use.”

## 0:15–0:35 — The Problem

**On screen:** Show the synthetic **Drone Detection Project** conversation.

**Narration:** “In an older conversation, I documented this drone-detection setup: a Raspberry Pi 4 streams the camera footage, a Windows laptop with CUDA performs inference, and a pan-tilt mount tracks the detected aircraft. That context exists in my history, but it is not available in a fresh chat.”

## 0:35–1:15 — Core Demo

**On screen:** Open a fresh ChatGPT conversation. Type, but do not submit:

> Where was I running my model again?

**Narration:** “This question only makes sense if the AI knows which project I'm referring to.”

**Action:** Click **Retrieve Memory**.

**On screen:** Show **Drone Detection Project** and the relevant retrieved details.

**Narration:** “Memora semantically searched my previous conversations and found the relevant project without requiring the exact original wording. It retrieves a focused result with source provenance instead of dumping my entire history into the prompt.”

## 1:15–1:40 — Use This Context

**Action:** Click **Use This Context** and show the compact context inserted before the original question.

**Narration:** “Memora never automatically sends anything. Retrieval is explicit, context insertion is a separate explicit action, and I stay in control of when the message is submitted.”

**Action:** Review the draft, then submit manually.

## 1:40–2:05 — History Import

**On screen:** Open the Memora extension popup and point to **Import ChatGPT history**.

**Narration:** “Users can explicitly select a supported ChatGPT JSON or ZIP export. Memora sends it to their local backend, reconstructs the conversations, prevents unchanged duplicate imports, and indexes the history into searchable memory. It does not automatically access the user's ChatGPT account.”

Do not run a large live import during the recording.

## 2:05–2:30 — Architecture and Validation

**On screen:** Show the architecture diagram or repository overview.

**Narration:** “The Manifest V3 extension talks through its service worker to a local FastAPI backend. OpenAI embeddings power semantic RAG, and SQLite stores user-scoped conversation chunks and provenance. On our small 15-query MVP evaluation, the local lexical baseline achieved 46.7 percent Top-1 accuracy, while OpenAI semantic embeddings achieved 100 percent Top-1 and Top-3. This is a focused MVP evaluation, not a production benchmark.”

## 2:30–End — Closing

**On screen:** Return to the ChatGPT answer and Memora panel.

**Narration:** “Memora gives AI continuity across conversations while keeping memory retrieval under the user's control.”

## Demo Checklist

Before recording:

- [ ] Local backend is running on `http://127.0.0.1:8765`.
- [ ] A fresh private OpenAI API key is configured only in the backend shell.
- [ ] The production extension is rebuilt and reloaded in `chrome://extensions`.
- [ ] The ChatGPT tab is refreshed after the extension reload.
- [ ] **Drone Detection Project** is indexed for the backend's configured `demo-user` identity.
- [ ] The same private Memora local token is configured in the backend shell and extension popup.
- [ ] The popup reports **Connected**.
- [ ] `Where was I running my model again?` is copied and ready.
- [ ] **Retrieve Memory** has been tested once.
- [ ] **Use This Context** has been tested once.
- [ ] No real export, API key, console containing sensitive data, or personal database is visible on screen.

## Emergency Fallback

If OpenAI retrieval fails during recording, keep the already indexed database, confirm the backend is still running, and retry once. If the failure persists, pause recording and verify the API key, billing/quota, provider/model settings, and network connection. Do not modify application code during the recording.
