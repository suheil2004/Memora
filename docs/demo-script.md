# Memora 2–3 Minute Demo Script

## Before presenting

- Start the backend on `http://127.0.0.1:8765` with OpenAI embeddings.
- Confirm the extension popup says **Connected** and uses `demo-user`.
- Index the synthetic samples and verify the drone query ranks correctly.
- Open a clean ChatGPT conversation.

## Script

1. **Problem (15 seconds):** “AI assistants lose context between conversations, so we repeatedly explain the same projects and decisions.”
2. Briefly show the safe stored conversation **Drone Detection Project**. Point out that the Raspberry Pi 4 streams the camera while the Windows CUDA laptop runs inference.
3. Open a fresh ChatGPT conversation and type, without submitting: `Where was I running my model again?`
4. Explain: “That old project conversation is not in this new chat's context.”
5. Click **Retrieve Memory** in the Memora panel.
6. Show **Drone Detection Project** as the top match and the Raspberry Pi / Windows CUDA details.
7. Click **Use This Context**.
8. Show that Memora inserted a compact attributed context block before the original draft.
9. Manually submit the prompt. Emphasize that Memora never submits automatically.
10. Briefly open the extension popup and show the explicit ChatGPT history import control.
11. Close with: “Memora gives AI continuity across conversations while keeping retrieval under explicit user control.”

If retrieval fails, check the popup connection state, confirm the backend port is `8765`, then reload the extension and refresh ChatGPT.

