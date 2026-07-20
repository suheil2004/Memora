# Memora 90-Second Demo Video Script

Use a rehearsed synthetic or sanitized local database containing an original project design, an explicit updated/current design, and—when reliable—one recovered text PDF with page provenance. Do not run history import live.

## 0:00–0:12 — Forgotten context

**On screen:** Briefly show an old project conversation, its later update/correction, and a historical PDF filename.

**Narration:** “Important context gets stranded across old AI conversations: the original plan, what changed, and the document that explained why.”

## 0:12–0:22 — Fresh conversation

**On screen:** Open fresh ChatGPT and type, without submitting:

> What is the current drone inference setup, and what changed from the original design?

**Narration:** “In a fresh chat, this question is ambiguous unless the assistant knows both versions.”

## 0:22–0:43 — Explicit retrieval

**Action:** Click **Retrieve Memory**.

**Narration:** “Memora retrieves relevant evidence, separates distinct versions, identifies important facts, and prepares one sourced brief per memory.”

If elapsed-time loading copy appears, do not call it live backend progress. It is calm feedback while retrieval runs.

## 0:43–1:04 — Show the difference

**On screen:** Show the current-state MemoryBrief first, the historical related memory separately, and the **Discussed** timestamp. Expand **Sources** to reveal old/new conversations and, if present, the recovered PDF page.

**Narration:** “The current design ranks first, the original remains available for a historical question, and every source is attached by Memora—not invented by the model. This is more than nearest-vector text.”

## 1:04–1:22 — User-controlled insertion

**Action:** Click **Use This Context**. Highlight the bounded selected brief and unchanged original question in the composer.

**Narration:** “Only the memory I selected enters the draft. Memora treats history as untrusted reference data, and it never presses Send.”

Do not submit automatically. A manual click may be shown only after reviewing the draft.

## 1:22–1:30 — Trust and close

**On screen:** Briefly show popup **Ready** status and **Privacy & Memory** counts/clear control, then return to the panel.

**Narration:** “Memory is imported explicitly, sourced, inspectable, clearable, and always offered to the user.”

## Deterministic fallback

If the temporal/PDF fixture is not fully reliable, use the proven question:

> Where was I running my model again?

Show **Drone Detection Project**, Raspberry Pi camera streaming, Windows CUDA inference, sources, and explicit insertion. A simpler reliable flow is preferable to an intermittent complex one.

## Recording checklist

- [ ] Use a clean checkout and synthetic/sanitized demo database—not personal history.
- [ ] Backend is bound to `http://127.0.0.1:8765` with provider configuration and quota validated.
- [ ] Extension is built, reloaded in `chrome://extensions`, and the ChatGPT tab refreshed.
- [ ] The popup reports **Ready**, using the same private local token as the backend.
- [ ] Exact query, card ordering, current/historical sources, timestamps, insertion text, and fallback query are prevalidated.
- [ ] No API key, bearer token, local path, console, browser-profile data, or real user content is visible.
- [ ] Capture the panel, insertion result, and privacy/readiness popup as separate still images after recording.
