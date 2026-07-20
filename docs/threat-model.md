# Memora Threat Model

## Scope

This threat model covers the Memora repository, a locally running backend, the locally loaded Chrome extension, synthetic users/data, SQLite, and normal documented use of the configured embedding provider. It does not cover attacks against ChatGPT, OpenAI, external systems, or other users' data.

## System Summary

```text
ChatGPT page
  -> Memora content script
  -> chrome.runtime messaging
  -> Manifest V3 service worker
  -> local FastAPI API
  -> embedding provider
  -> semantic or exact entity-scoped retrieval over SQLite
  -> MemoryThread grouping and per-thread synthesis
  -> sourced MemoryBrief cards
  -> explicit insertion into ChatGPT draft

User-selected JSON/ZIP export
  -> FastAPI upload endpoint
  -> importer and graph normalization
  -> message-aware chunking
  -> embeddings
  -> SQLite
```

## Assets

| Asset | Security need |
| --- | --- |
| Imported conversation history | Confidentiality, integrity, deletion, provenance |
| Retrieved memory/context | Confidentiality, integrity, correct user scope |
| SQLite database and sidecar files | Confidentiality, integrity, availability |
| OpenAI API key | Confidentiality and backend-only use |
| OpenAI quota/credits | Protection from unauthorized consumption |
| Extension settings | Integrity; confidentiality of identifiers where appropriate |
| Local backend | Availability, restricted reachability, correct configuration |
| Server-configured `MEMORA_USER_ID` | Integrity as the effective local database scope |
| Memora local token | Confidentiality; local API authentication only |
| Imported files | Safe parsing, bounded resource use, no unintended persistence |
| Extracted PDF text and document provenance | Confidentiality, integrity, user scope, bounded processing |
| Historical attachment metadata and opaque export assets | Correct conversation ownership, path containment, ambiguity refusal |
| Retrieval provenance | Integrity and correct association with source/user |

## Trust Boundaries

1. **ChatGPT webpage ↔ content script:** Page DOM and draft text are untrusted. Chrome's isolated world limits direct JavaScript access, but the content script deliberately reads and writes page DOM.
2. **Content script ↔ service worker:** Runtime messages are an internal privilege boundary. Message bodies and sender context must be treated as untrusted.
3. **Extension ↔ FastAPI:** Local HTTP is not inherently trusted. Host permissions and CORS control browser access but do not authenticate callers.
4. **FastAPI ↔ SQLite:** Input must remain parameterized and every operation must scope by the authenticated principal—not merely a caller-supplied identifier.
5. **FastAPI ↔ OpenAI API:** The backend holds the key and controls the endpoint/model, but untrusted text can consume quota and is sent to the configured provider for embedding.
6. **Uploaded export ↔ importer:** File names, archive metadata, JSON shape, graph links, and message content are untrusted.
7. **Retrieved history ↔ current LLM prompt:** Historical text is data from a different trust context and can contain instruction-like content.

## Attacker Models

- Malicious content executing on a supported AI-chat page.
- A malformed or unexpected internal runtime message.
- A local process or local browser origin able to reach the backend.
- A direct API caller attempting missing, malformed, or invalid authentication.
- A caller attempting to inject a `user_id` despite server-derived scope.
- A malicious or corrupted ChatGPT export.
- Instruction-like text stored in historical conversations.
- A caller attempting to consume embedding quota or exhaust local resources.
- Accidental developer secret leakage through files, logs, documentation, bundles, or source maps.

## Attack Surfaces

- `GET /health`, `/docs`, and `/openapi.json`
- `POST /api/v1/conversations/import`
- `POST /api/v1/import/chatgpt`
- `POST /api/v1/context/retrieve`
- Multipart parsing and in-memory upload collection
- Local PDF parsing of untrusted text-based documents
- Conservative correlation of untrusted ChatGPT attachment, library, filename-map, and manifest metadata
- JSON and ZIP parsing, archive metadata, graph traversal, and normalization
- SQLite reads/writes and embedding serialization
- Extension popup settings and file picker
- `chrome.runtime.onMessage` request validation
- Service-worker backend HTTP client
- ChatGPT draft extraction and context insertion
- Environment variables, local databases, build output, source maps, and logs
- Python and npm dependency supply chains

## Abuse Cases

| Abuse case | Current control | Residual risk |
| --- | --- | --- |
| Choose another user's ID and retrieve history | Sensitive routes authenticate; request schemas reject `user_id`; scope comes from `MEMORA_USER_ID` | Local token is one shared capability, not multi-user identity |
| Replace another user's conversation | Same server-derived scope applies to import/replacement | Anyone holding the local token has the single configured user's authority |
| Consume OpenAI credits repeatedly | Authentication plus in-process retrieval/import limits | Per-process limiter is not distributed or durable |
| Send a very large query/conversation | 2,000-character query cap, top-k 1–10, message/file limits | Aggregate import allowance remains intentionally generous for local history files |
| ZIP traversal or decompression bomb | No extraction; traversal, entry, per-file, and declared uncompressed limits | Upload is still read into memory; parser/resource risk remains bounded but material |
| SQL injection through identifiers/text | Parameterized SQL | Low residual injection risk in reviewed queries |
| Script injection in extension UI | Dynamic values use `textContent`; Shadow DOM panel | Low residual DOM injection risk in reviewed rendering |
| Indirect prompt injection from memory | Per-thread synthesis boundary, trusted provenance attachment, explicit untrusted-data warning, escaped memory delimiters, separate question, explicit insertion | LLMs may still follow instruction-like data |
| Service worker fetches arbitrary targets | Exact localhost:8765 URL validation plus narrow manifest permissions | Compromised extension context can still call the configured local API with its stored token |
| Secret leaks into browser bundle | Key only read server-side; ignores and scan | Developer process/source-map mistakes remain possible |
| Backend exposed to LAN | Documentation uses `127.0.0.1` | Launching Uvicorn on `0.0.0.0` expands every unauthenticated risk |

## Security Assumptions

- The demo backend is bound only to `127.0.0.1` and is not reverse-proxied or port-forwarded.
- The workstation, Chrome profile, extension installation, and local filesystem are controlled by the demo operator.
- Only synthetic data is used during assessment and public demonstration.
- The OpenAI key is fresh, private, server-side, scoped/limited where the provider supports it, and never shown on screen.
- The configured database belongs to the current demo operator.
- Chrome enforces Manifest V3 isolated worlds, runtime messaging boundaries, and declared host permissions.
- The embedding provider is trusted to process text under its own terms; Memora does not provide end-to-end encryption.
- CORS is treated as a browser-origin control, not authentication.
- The Memora local token and `MEMORA_USER_ID` are configured privately in the backend environment; the matching token is stored only in the local Chrome profile.

## Out-of-Scope Assumptions That Must Not Become Deployment Defaults

The controlled-local-demo assumptions are not suitable for multi-user, LAN, hosted, or cloud operation. Any such deployment requires authenticated identity, server-derived authorization scope, abuse controls, encrypted transport appropriate to the environment, secure storage/lifecycle design, and a broader operational threat model.
