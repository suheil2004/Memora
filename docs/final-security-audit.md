# Final Security Hardening Audit

## Result and scope

This authorized review covered the complete local Chrome-extension/FastAPI/SQLite MVP using source inspection, synthetic fixtures, disposable databases, local/mock providers, dependency advisory services, and production builds. It did not open or mutate the user's real database, delete real memory, or call OpenAI.

Final unresolved findings: **0 Critical, 0 High, 1 Medium, 3 Low, and 4 Informational**. The controlled loopback-only hackathon MVP is reasonably hardened under its documented assumptions. This assessment is not approval for LAN, public, cloud, or real multi-user deployment.

## Endpoint inventory

| Endpoint | Classification | Control |
| --- | --- | --- |
| `GET /health` | Public, non-sensitive | Returns static availability only |
| `GET /api/v1/memory/stats` | Authenticated, sensitive | Bearer token; server-derived user; aggregate counts only |
| `DELETE /api/v1/memory` | Authenticated, destructive | Bearer token; server-derived user; body and `user_id` query rejected; transactional scoped deletion |
| `POST /api/v1/conversations/import` | Authenticated, sensitive/expensive | Bearer token; strict schema; import rate limit |
| `POST /api/v1/context/retrieve` | Authenticated, sensitive/expensive | Bearer token; bounded request; retrieval rate limit |
| `POST /api/v1/import/chatgpt` | Authenticated, sensitive/expensive | Bearer token; bounded files/read/archive; import rate limit |
| `POST /api/v1/import/documents` | Authenticated, sensitive/expensive | Bearer token; PDF limits; import rate limit |

The token is compared with `secrets.compare_digest`. Missing, empty, malformed, wrong, duplicated, and very long credentials fail closed; exactly one valid bearer value is required. API callers cannot select a user.

## Fixed findings

### AUTH-001: duplicate Authorization ambiguity — Low — Fixed

FastAPI's former scalar header binding selected one value when duplicate Authorization headers were supplied. A proxy/client disagreement could make that ambiguity security-relevant. Every sensitive route now collects all Authorization values, and authentication accepts exactly one. Regression tests cover duplicates, oversized values, missing credentials, and all sensitive endpoints.

### RES-001: unbounded pre-check upload read — Low — Fixed

The ChatGPT multipart route previously used an unbounded `UploadFile.read()` and checked the aggregate limit afterward. A local authenticated caller could cause excess application-memory allocation before receiving 413. Reads are now limited to the remaining configured aggregate allowance plus one byte. Archive entry count, declared uncompressed size, JSON size, and traversal checks remain intact.

### PERM-001: unnecessary Chrome `tabs` permission — Low — Fixed

The privacy UI queried tabs by URL only to clear visible cards. It now queries tab IDs without inspecting privileged URL/title fields and broadcasts the exact internal control message; tabs without Memora content scripts simply reject via `Promise.allSettled`. The manifest continues to request only `storage`, plus the existing narrow host permissions; no `tabs` permission is required.

### DEP-001: esbuild development-server advisory — Low — Fixed

`npm audit` identified GHSA-g7r4-m6w7-qqqr in the direct development dependency. Memora used only the build API, but a compatible fix was available. esbuild and its lockfile were updated to 0.28.1; the final npm audit reports zero vulnerabilities.

### IGNORE-001: opaque export assets — Informational — Fixed

`.gitignore` now explicitly excludes `*.dat` and extracted `chatgpt-export*/` directories in addition to environments, databases/sidecars, exports, archives, documents, caches, and build artifacts. Tracked sanitized fixtures remain available.

## Remaining findings

### PI-001: indirect prompt injection — Medium — Remaining/accepted for local MVP

Historical conversations and PDF text are untrusted and may contain persuasive instructions. Memora bounds and escapes evidence, uses structured schemas, synthesizes one thread at a time, attaches provenance only in backend code, filters instruction-like deterministic fallback lines, and requires explicit insertion without submission. These controls reduce risk but cannot guarantee a downstream model ignores malicious historical text.

### LOCAL-001: plaintext local secrets and memory — Low — Remaining

The local token resides in extension-owned `chrome.storage.local`, restricted to trusted extension contexts; the OpenAI key remains only in the backend environment. SQLite text, embeddings, and provenance are not encrypted at rest, and browser-profile/filesystem compromise can expose them. `secure_delete` is defense in depth and cannot erase backups, snapshots, WAL remnants, or storage-device history.

### DEPLOY-001: development CORS/API surface — Low — Remaining for local MVP; production blocker

CORS allows only configured origins, no credentials, and only GET/POST/DELETE plus Authorization/Content-Type. An unlisted malicious origin receives no `Access-Control-Allow-Origin`; bearer authentication remains the real control. Default development origins and public FastAPI docs are acceptable only while bound to `127.0.0.1`. Do not expose this configuration to a LAN or public network.

### RATE-001: process-local throttling — Low — Remaining for local MVP; production blocker

Retrieval and imports are separately bounded before provider work, but the limiter resets on restart and is not shared across workers. Public deployment needs durable quotas, concurrency/backpressure, timeouts, and provider spending controls.

## Trust-boundary conclusions

- **Token flow:** entered in the extension popup, stored in `chrome.storage.local`, read only by trusted extension contexts, and transmitted only as an Authorization header from popup/service worker to exact `http://localhost:8765` or `http://127.0.0.1:8765`. It is absent from page storage, query strings, runtime messages, logs, DOM attributes, and bundles. The password field is populated only inside the isolated popup while open.
- **Messaging:** no `window.postMessage`, page CustomEvent bridge, or `externally_connectable` surface exists. Retrieval accepts an exact bounded two-field internal message. The clear-state message has an exact one-field schema and cannot delete data; deletion occurs only from the authenticated popup client.
- **Host/local API:** manifest access is loopback HTTP only; runtime validation fixes host, port, scheme, and path. Documentation consistently starts Uvicorn on `127.0.0.1`. Host headers are not trusted for authentication.
- **Paths/archives:** ZIPs are inspected in memory and never extracted. Absolute/traversal paths, excessive entries, excessive declared expansion, oversized JSON/PDFs, malformed/encrypted/no-text PDFs, ambiguous attachment matches, symlinks, and export-root escapes fail safely. PDF content must start with a PDF signature.
- **XSS:** all model/history-derived titles, summaries, details, filenames, provenance, and errors use `textContent`; `innerHTML` is limited to static panel markup/styles. Script, image-handler, entity, and SVG-like payloads render as text.
- **Stats/delete:** statistics expose only five aggregate counts. Deletion is authenticated, server-scoped, transactional, idempotent, rejects body/query targeting, clears stored rows/caches in scope, and never deletes files or backups.
- **Logging/errors/secrets:** server logs contain operation completion/counts only. Production errors omit stack traces, SQL, request bodies, paths, tokens, provider payloads, and stored content. Tracked-file scans found no OpenAI-shaped key or non-empty token assignment.
- **Provider processing:** local storage is distinct from provider processing. With OpenAI configured, bounded chunk text is sent for embeddings; bounded per-thread evidence is sent for MemoryFact extraction and MemoryBrief synthesis. The backend key/model stay server-side, and no provider payload is logged. Local deterministic providers avoid those external calls.
- **Build:** the production extension has no embedded key/token, remote executable JavaScript, `eval`, or `new Function`. Source maps contain source code but no detected secrets and `dist` remains ignored.

## Informational observations

1. `/health`, `/docs`, and `/openapi.json` reveal only service/schema availability locally; sensitive operations still authenticate.
2. Extension source maps improve debugging but expose source to anyone with the unpacked build; no secrets were found.
3. Manual backups and OneDrive/filesystem history remain outside Memora's deletion guarantee.
4. `python -m pip check` passed; project-scoped `pip-audit` and final `npm audit` found zero known vulnerabilities. Advisory checks are point-in-time only.

## Public/cloud production blockers

Before public or multi-user use: replace the shared capability with real identity/session/rotation/revocation; add TLS and explicit listener/firewall/proxy policy; use durable distributed quotas and async bounded import processing; implement tenant isolation throughout; add managed encryption/key/backup/retention controls; lock production CORS and API documentation; establish dependency/SBOM monitoring and signed extension releases; add redacted operational auditing and incident response; and treat tool-capable downstream prompt injection as a formal policy boundary.

## Verification

- Backend: 101 tests passed; Python compilation passed.
- Extension: 57 tests passed across 9 files; strict TypeScript typecheck passed; production build passed and regenerated `dist`.
- Dependency checks: project-scoped `pip-audit` 0; final `npm audit` 0 Critical/High/Moderate/Low.
- Repository: `git diff --check` passed.
