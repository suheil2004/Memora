# Security Policy

## Supported version

Memora is an active local-first hackathon MVP. Security fixes apply to the latest code on the default branch; older commits and informal builds are not supported releases.

## Reporting a vulnerability

Please use GitHub Private Vulnerability Reporting for this repository. Do not publish proof-of-concept details, API keys, Memora tokens, conversation content, database files, exports, or other sensitive data in a public issue.

Include the affected component, reproduction steps using synthetic data, expected impact, and any suggested remediation. Reports will be reviewed as availability permits; an initial response is targeted within five business days but is not guaranteed by a formal service-level agreement.

## Current security boundary

The current design is a single-user local application:

- FastAPI is launched on `127.0.0.1:8765`.
- Sensitive API routes require one dedicated local bearer token.
- API callers cannot select `user_id`; scope comes from backend configuration.
- The extension permits only the fixed localhost backend and keeps the OpenAI key out of extension code and storage.
- Imports, queries, context output, archives, and PDF processing are bounded.
- Validation and general API errors are sanitized.
- Retrieved history is treated as untrusted evidence, and trusted provenance is attached by backend code.
- Retrieval, context insertion, ChatGPT submission, import, and deletion remain separate user actions.

These controls do not make Memora production-ready. The shared local token is capability-style authentication, in-process rate limits are not durable, SQLite and saved local credentials are not encrypted by Memora, and loopback HTTP does not provide TLS. Do not expose the MVP to a LAN or public network.

## Important residual risks

- Historical content can contain indirect prompt injection. Bounded evidence, delimiters, synthesis isolation, and explicit insertion reduce but do not eliminate that risk.
- Anyone with access to the workstation, Chrome profile, local token, `.env`, database, exports, or backups may gain sensitive access.
- Deletion clears the configured user's active database rows; it cannot erase manual copies, backups, snapshots, provider retention, or text already inserted into ChatGPT.
- ChatGPT DOM changes can break or alter extension behavior.
- Dependency and advisory results are point-in-time observations, not ongoing guarantees.

Before public or multi-user deployment, Memora would require production identity and session management, token rotation/revocation, TLS, explicit network policy, durable quotas, tenant isolation, managed secrets and encryption, backup/retention controls, operational monitoring, and a formal prompt-injection policy.

## Responsible disclosure

Please allow reasonable time for investigation and remediation before public disclosure. Confirmed issues may be documented through a security advisory after a fix is available.
