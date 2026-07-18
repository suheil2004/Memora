# Memora Defensive Security Audit

## Executive Summary

This authorized review assessed the local Memora repository and application using source inspection, existing automated tests, disposable SQLite databases, local FastAPI test clients, mocked/local embeddings, synthetic users, and synthetic instruction-like content. No external application was attacked, no real user data was accessed, and no live OpenAI embedding request was made.

The implementation has sound user-scoped SQL, parameterized queries, bounded top-k/context output, safe ZIP non-extraction, sanitized general errors, browser-side text rendering, and backend-only key handling. The primary issue is architectural: `user_id` is accepted as an identity claim without authentication. Consequently, correct database filtering does not prevent a caller from selecting another user's scope. Unauthenticated endpoints and unbounded text inputs also expose API-credit and resource-abuse paths.

For a controlled local demo bound to `127.0.0.1`, using synthetic data and a limited API key, the MVP is acceptable with operational precautions. It is not safe for LAN, hosted, shared-machine, or real multi-user deployment in its current form.

## Method and Safe Evidence

- Ran all 31 backend tests with deterministic local embeddings: all passed.
- Inspected extension runtime contracts, settings, host permissions, HTTP client, DOM rendering, and insertion logic.
- Used synthetic `user-a`, `user-b`, SQL-like strings, and a disposable test database.
- Confirmed unauthenticated health/import/retrieve calls returned HTTP 200.
- Confirmed selecting either synthetic `user_id` returned that user's data; an unrelated scope returned no data.
- Confirmed SQL-like input remained inert and returned no cross-user results.
- Confirmed `top_k=51` returned 422, while a 100,000-character query returned 200 and was embedded locally.
- Confirmed synthetic instruction-like history was retrieved inside `[Memora Context]` but lacked an explicit untrusted-data label.
- Confirmed an unlisted CORS preflight returned 400 and no allow-origin header; a direct non-browser request still executed.
- Performed filename-only secret scans across tracked/untracked files and `extension/dist` without printing values.
- Ran `pip-audit` against the project: no known Python dependency vulnerabilities were reported.
- Ran `npm audit --package-lock-only`: one low-severity direct development dependency advisory was reported for esbuild.

## Findings Summary

Severity describes impact; priority describes when the team chose to remediate. There is no count inconsistency: the three P1 items consist of two High findings and one Medium finding.

| ID | Severity | Title | Priority | Remediation status |
| --- | --- | --- | --- | --- |
| SEC-001 | High | Unauthenticated client-controlled `user_id` enables BOLA/IDOR | P1 | **FIXED** for local single-user MVP |
| SEC-002 | High | Unauthenticated, unthrottled embedding and import operations enable quota/resource abuse | P1 | **MITIGATED** |
| SEC-003 | Medium | Retrieved historical text can act as indirect prompt injection | P1 | **MITIGATED** |
| SEC-004 | Low | Extension runtime messages have incomplete defensive validation | P2 | **FIXED** |
| SEC-005 | Low | Backend URL validation is broader than the intended localhost trust boundary | P2 | **FIXED** |
| SEC-006 | Low | CORS includes development origins and does not reduce direct-local attack exposure | P2 | **MITIGATED** by authentication; CORS cleanup deferred |
| SEC-007 | Low | Sensitive SQLite data is stored without encryption or access lifecycle controls | Future | **ACCEPTED RISK / DEFERRED** |
| SEC-008 | Low | Locked esbuild version has a development-server advisory | P2 | **DEFERRED** |
| SEC-009 | Informational | API schema/docs are exposed and security headers are minimal | Future | **ACCEPTED RISK / DEFERRED** |

Post-remediation architecture is documented in [security-architecture.md](security-architecture.md). Original reproduction evidence below is retained as the audit record.

## Detailed Findings

### SEC-001 — Unauthenticated client-controlled `user_id` enables BOLA/IDOR

- **Status:** **FIXED** for the controlled local single-user MVP. Sensitive routes now require a constant-time-checked bearer token, remove `user_id` from request schemas, reject spoofed extra fields, and use server-side `MEMORA_USER_ID`. This is not production multi-user authentication.

- **Severity:** High
- **Affected component:** FastAPI import/retrieval endpoints, extension settings, service composition
- **Attack precondition:** Ability to reach the local API and know or guess a target `user_id`
- **Impact:** Read another scope's conversation chunks/context; import or replace conversations inside that scope; consume operations as that user
- **Safe reproduction performed:** Imported distinct synthetic conversations for `user-a` and `user-b` without credentials. Retrieval requests that supplied each ID returned that ID's result. No authentication token, session, or principal was present.
- **Evidence:** `ConversationImportRequest`, `ContextRetrieveRequest`, and multipart import accept `user_id` directly. `background-handler.ts` reads it from editable extension settings. Database queries correctly filter using the supplied value.
- **Root cause:** `user_id` is a caller-provided storage partition, not an authenticated server-derived principal.
- **Classification:** Authentication weakness plus broken object-level authorization (BOLA/IDOR). The SQL scoping itself is not flawed.
- **Recommended remediation:** Before any non-demo/shared deployment, authenticate the caller, derive the user scope server-side, ignore client attempts to select another principal, and authorize every read/write/replacement/deletion against that principal. Consider a random local bearer capability as a minimal single-user bridge, but do not present it as multi-user authentication.
- **Hackathon priority:** P1. Operationally contain for the demo; P0 before exposing beyond localhost or using real multi-user data.

### SEC-002 — Unauthenticated, unthrottled embedding and import operations enable quota/resource abuse

- **Status:** **MITIGATED.** Authentication is required; query length is capped at 2,000, `top_k` at 1–10, direct message content/count are bounded, selected files are capped at 10, and generous in-process retrieval/import limits return 429 before embedding. Distributed abuse protection remains deferred.

- **Severity:** High
- **Affected component:** Retrieval API, direct conversation import, ChatGPT multipart import, embedding provider, SQLite
- **Attack precondition:** Ability to reach the local API
- **Impact:** OpenAI credit consumption, synchronous worker occupation, memory/CPU pressure, and database growth
- **Safe reproduction performed:** A 100,000-character synthetic query was accepted with HTTP 200 using local embeddings. Repeated unauthenticated import/retrieve calls were accepted. No live OpenAI calls or significant load were generated.
- **Evidence:** Query, user ID, conversation title/ID, message content, message count, and direct JSON request body have no practical maximum. `top_k` is capped at 50 and context at 50,000 characters. Multipart aggregate content is capped at 250 MiB, ZIP entries at 1,000, declared uncompressed ZIP data at 200 MiB, and JSON members at 50 MiB; however each upload is read fully before aggregate rejection and there is no upload-count/rate limit.
- **Root cause:** Local-MVP trust assumptions; no authentication, rate limiting, request middleware limit, per-user quota, or bounded text schema.
- **Recommended remediation:** Add request/body and field limits before embedding, upload-count/conversation/message limits, streaming or early multipart enforcement, rate/concurrency controls, per-principal quotas, and bounded retries/timeouts. Couple credit-consuming operations to authenticated authorization.
- **Hackathon priority:** P1. For the controlled demo, bind to loopback, close unrelated local services/pages, use a provider spending limit, and pre-index data.

### SEC-003 — Retrieved historical text can act as indirect prompt injection

- **Status:** **MITIGATED.** Inserted context now explicitly calls history untrusted reference data, says not to follow contained instructions, escapes forged delimiter strings, encloses it in `<historical_memory>`, and separates the current question. Prompt injection cannot be completely prevented.

- **Severity:** Medium
- **Affected component:** Raw-conversation RAG, context builder, context insertion
- **Attack precondition:** Instruction-like content exists in imported history and is semantically retrieved; user clicks both retrieve and insert
- **Impact:** The downstream LLM may interpret historical data as instructions, potentially changing its response or encouraging unintended disclosure/actions within the chat context
- **Safe reproduction performed:** Imported a synthetic historical sentence asking later instructions to be ignored. It was retrieved and included inside `[Memora Context]`. The extension converted the sentence into a bullet under “Relevant context from my previous conversations,” but did not explicitly label it untrusted or tell the model not to follow embedded instructions.
- **Evidence:** `CompactContextBuilder` copies role-prefixed source lines. `extractContextPoints` removes role labels, and `createContextSnapshot` inserts the remaining text as bullets.
- **Root cause:** Retrieved raw text crosses into the current prompt without a strong data/instruction boundary or content-risk treatment.
- **Recommended remediation:** Mark retrieved material as untrusted quoted reference data, preserve source/role, add a clear instruction not to follow directives inside memory, visually warn on instruction-like content, and consider filtering/risk scoring. Retain explicit insertion and manual submission. Prompt injection cannot be perfectly prevented.
- **Hackathon priority:** P1 for demos using arbitrary exports; risk is lower with curated synthetic data.

### SEC-004 — Extension runtime messages have incomplete defensive validation

- **Status:** **FIXED.** The listener now requires the exact two-field message shape, known type, nonblank string query, and 2,000-character maximum; settings validate token presence and `top_k` 1–10.

- **Severity:** Low
- **Affected component:** `background-listener.ts`, settings validation, service-worker handler
- **Attack precondition:** Ability to send an internal extension message or influence an accepted query through the supported page and user click
- **Impact:** Oversized queries can reach the backend; unexpected fields are accepted; validation relies on downstream layers and Chrome's current messaging boundary
- **Safe reproduction performed:** Static validation matrix: unknown type, missing query, and non-string query are rejected; extra properties and arbitrarily long strings pass `isRetrieveRequest`. `top_k` is not part of the runtime message; stored positive integers have no extension-side upper bound, though FastAPI rejects values above 50.
- **Evidence:** Runtime predicate checks only object/non-null, exact type, and string query. It does not check sender, exact keys, length, or normalized emptiness.
- **Root cause:** Minimal functional type guard rather than a complete runtime schema.
- **Recommended remediation:** Validate sender identity/context, exact message shape, query length/non-blank value, and bounded settings before privileged work. Continue enforcing all bounds again on the backend.
- **Hackathon priority:** P2.

### SEC-005 — Backend URL validation is broader than the intended localhost trust boundary

- **Status:** **FIXED.** Runtime configuration accepts only `http://127.0.0.1:8765` or `http://localhost:8765`, without credentials, paths, queries, or fragments.

- **Severity:** Low
- **Affected component:** Extension settings, service-worker permission check, popup API client
- **Attack precondition:** Ability to modify extension settings or future expansion of host permissions
- **Impact:** If permissions are broadened later, the service worker/popup could send Memora request bodies or selected files to an unintended HTTP(S) destination
- **Safe reproduction performed:** Static review only; no external request was made. `normalizeBackendUrl` accepts any HTTP(S) hostname. Current manifest permissions and `chrome.permissions.contains` restrict service-worker access to HTTP `127.0.0.1` and `localhost`, so an arbitrary external destination is not currently reachable through normal extension operation.
- **Evidence:** URL validation checks scheme only; manifest host permissions supply the effective localhost control.
- **Root cause:** Intended trust policy is encoded indirectly in manifest permissions rather than URL validation shared by all clients.
- **Recommended remediation:** Explicitly allow only `127.0.0.1` and `localhost`, reject credentials/fragments and unexpected schemes, define the acceptable port policy, and share validation across popup/background. Keep manifest permissions narrow.
- **Hackathon priority:** P2 defense in depth; current manifest substantially mitigates exploitation.

### SEC-006 — CORS includes development origins and does not reduce direct-local attack exposure

- **Status:** **MITIGATED.** Sensitive operations now require the local bearer token even when CORS permits an origin. Default-origin cleanup remains P2, and loopback-only binding remains mandatory.

- **Severity:** Low
- **Affected component:** FastAPI CORS configuration and deployment instructions
- **Attack precondition:** A hostile page served from an allowed local origin, a misconfigured allowlist, or any non-browser local caller
- **Impact:** Browser-origin controls may permit an unintended local page; direct processes can invoke all endpoints regardless of CORS. Binding to `0.0.0.0` would expose unauthenticated operations to reachable network peers.
- **Safe reproduction performed:** Default `http://localhost:3000` received an allow-origin header. An unlisted origin's preflight returned 400 and no allow-origin header. A direct request still executed, demonstrating that CORS is not authorization. The service was not bound to a network interface during testing.
- **Evidence:** Default allowlist contains `localhost:3000` and `127.0.0.1:3000`; launch binding is controlled outside the application.
- **Root cause:** Development-origin defaults combined with reliance on loopback deployment rather than authenticated API access.
- **Recommended remediation:** Remove unused default origins for the demo, explicitly configure the exact extension origin when necessary, reject wildcard deployment configuration, and add a startup warning or launcher that binds loopback by default. Authentication remains necessary for broader exposure.
- **Hackathon priority:** P2. Never run the current MVP on `0.0.0.0`.

### SEC-007 — Sensitive SQLite data is stored without encryption or access lifecycle controls

- **Status:** **ACCEPTED RISK / DEFERRED** for synthetic local demo data.

- **Severity:** Low
- **Affected component:** SQLite database and local filesystem
- **Attack precondition:** Local filesystem access, backup access, or accidental database sharing
- **Impact:** Disclosure of conversation text, embeddings, identifiers, and provenance; persistent data may outlive the demo
- **Safe reproduction performed:** Schema/source inspection only; no real database contents were opened or disclosed.
- **Evidence:** Message and chunk content and serialized embeddings are stored in ordinary SQLite. Database files and sidecars are Git-ignored, but no encryption, retention, inspection UI, or secure deletion workflow is implemented.
- **Root cause:** Explicit local hackathon scope and deferred data-lifecycle features.
- **Recommended remediation:** Define retention/deletion controls, restrictive filesystem permissions, secure backup policy, and encrypted storage/key management appropriate to the deployment threat model. Do not claim end-to-end encryption.
- **Hackathon priority:** Future for synthetic demo data; higher before importing sensitive real history.

### SEC-008 — Locked esbuild version has a development-server advisory

- **Status:** **DEFERRED.** The current workflow uses build-only esbuild, not its development server. Update remains a separate dependency-maintenance task.

- **Severity:** Low
- **Affected component:** Extension development dependency/tooling
- **Attack precondition:** A developer runs the affected esbuild development-server behavior on Windows under the advisory's local conditions
- **Impact:** The advisory describes a potential arbitrary file-read condition in the development server; it does not affect the built extension runtime directly
- **Safe reproduction performed:** `npm audit --package-lock-only --json`; no exploit attempt was made.
- **Evidence:** npm reported GHSA-g7r4-m6w7-qqqr for esbuild versions `>=0.27.3 <0.28.1`; the lock resolves an affected version. Memora's build script calls `build()` and does not start esbuild's development server.
- **Root cause:** A current advisory in a direct dev dependency.
- **Recommended remediation:** After review, update esbuild to a fixed compatible version and rerun extension tests, typecheck, and build. Avoid exposing development servers.
- **Hackathon priority:** P2; low practical exposure in the existing build-only workflow.

### SEC-009 — API schema/docs are exposed and security headers are minimal

- **Status:** **ACCEPTED RISK / DEFERRED** for the loopback development API.

- **Severity:** Informational
- **Affected component:** FastAPI configuration
- **Attack precondition:** Ability to reach the API
- **Impact:** `/docs` and `/openapi.json` make endpoint discovery easier; responses do not add a hardened header policy. This does not create access by itself.
- **Safe reproduction performed:** Local requests to `/docs` and `/openapi.json` returned 200. No debug stack trace was returned by reviewed endpoints.
- **Evidence:** Default FastAPI docs are enabled; no security-header middleware is configured; FastAPI debug mode is not enabled in application code.
- **Root cause:** Framework defaults suitable for local development.
- **Recommended remediation:** Disable docs in non-development deployments if not needed and add deployment-appropriate headers at the application or reverse proxy. Prioritize authentication and resource controls first.
- **Hackathon priority:** Future/Informational.

## Verified Controls and Negative Results

- **Database isolation implementation:** Search filters by `user_id` before ranking. Fingerprint lookup, conversation replacement, and deletion include user scope. Existing isolation tests pass. The remaining problem is identity proof, not missing SQL filters.
- **SQL injection:** Reviewed SQL uses parameters for untrusted values. Synthetic SQL-like identifiers/query text remained data and did not alter results or schema.
- **ZIP/file safety:** ZIPs are inspected in memory without extraction; absolute/parent paths, excess entries, oversized declared JSON members, excess declared uncompressed data, malformed archives/JSON, and unsupported types fail closed. Limits do not replace request-level abuse controls.
- **XSS/DOM injection:** Retrieved titles, points, statuses, and importer errors are assigned with `textContent`; the panel's only `innerHTML` is a static template/style.
- **Error leakage:** General import/retrieval exceptions become sanitized messages. Configuration errors reveal missing variable names but not values. No stack trace, database path, raw file body, or OpenAI key was observed in API responses.
- **Secret management:** No actual key-shaped token was found. Key assignments appear only as empty/example placeholders. `.env`, databases, exports, ZIPs, build artifacts, and source maps are ignored. No key-related pattern was found in `extension/dist`.
- **OpenAI boundary:** Key and model selection are server-side. Callers supply text and retrieval parameters only; they cannot select arbitrary OpenAI endpoints/request parameters or use Memora as a generic completion proxy. Unauthenticated text still consumes embedding quota (SEC-002).
- **Extension permissions:** Host access is limited to HTTP localhost/loopback. No `externally_connectable` entry is present, and external extension messages use a different Chrome event boundary.
- **Response validation:** Extension API responses validate result provenance types and finite scores before use.
- **Automated dependency review:** `pip-audit` reported no known vulnerabilities for the resolved Python project dependencies. npm reported only SEC-008. These are point-in-time advisory results, not guarantees.

## Test Additions

The original audit-only pass added no persistent test. Remediation added negative authentication/authorization tests, pre-embedding input/rate-limit tests, strict extension message/URL tests, untrusted-memory delimiter tests, bearer-header tests, and a production-build secret-pattern check. All use local or mocked embeddings.

## Post-Remediation Verification

- Backend: **37/37 tests passed**.
- Python compilation: **passed** for backend, scripts, and tests.
- Extension: **32/32 tests passed** across 8 files.
- TypeScript strict typecheck: **passed**.
- Production extension build: **passed**; required artifacts were regenerated.
- Build-time and repository secret-pattern checks: **passed** without printing credential values.
- Local five-conversation demo: **Drone Detection Project** remained the top result for “Where was I running my model again?”
- No automated test used live OpenAI embeddings or consumed API credits.

## Prioritized Remediation Guidance

### P0

None for a controlled, offline/local synthetic-data demonstration bound to `127.0.0.1`. The new local token is still insufficient for direct public/cloud or real multi-user exposure.

### P1

The three original P1 items are fixed or mitigated for the controlled local MVP. Public deployment still requires production identity, distributed quotas, and broader prompt-injection defenses.

### P2 / Future

Tighten extension runtime and URL validation, reduce default CORS origins, update esbuild after compatibility testing, define encrypted storage and lifecycle controls before real sensitive use, and disable development API surfaces where appropriate.

## Architectural Changes Required

Production-grade identity cannot be fixed only with validation: authentication and server-derived authorization scope require an architectural addition. Meaningful multi-user rate limits/quotas also depend on that principal. Encrypted storage and durable key management require a deliberate data-lifecycle design. Prompt-injection mitigation can be layered into the existing retrieval/insertion architecture but cannot guarantee elimination.

## Controlled Demo Decision

**Conditionally acceptable for a controlled local hackathon demo** if all of the following hold:

- bind Uvicorn only to `127.0.0.1`, never `0.0.0.0`;
- use synthetic pre-indexed data;
- use a fresh private API key with spending/quota safeguards and keep it off screen;
- close or distrust unrelated local web apps, especially allowed development origins;
- verify the extension URL and `demo-user` before presenting;
- do not import real personal history for the public demo;
- delete the disposable database afterward.

It is **not approved for hosted, LAN-accessible, shared-machine, or real multi-user use** before P1 remediation.
