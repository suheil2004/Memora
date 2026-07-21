# Security Policy

## Supported version

Memora is a local-first hackathon MVP that is still under active development. Security fixes apply to the latest code on the default branch. Older commits and informal builds are not treated as supported releases.

## Reporting a vulnerability

Use GitHub Private Vulnerability Reporting for this repository.

Please do not post proof-of-concept details, API keys, Memora tokens, conversation content, database files, exports, or any other sensitive data in a public issue.

When reporting a vulnerability, include:

- the affected component
- clear reproduction steps using synthetic data
- the expected impact
- any suggested fix, if you have one

The goal is to provide an initial response within five business days. This is a target, not a formal service-level agreement.

## Current security boundary

Memora is currently designed as a single-user local application.

- The FastAPI backend runs on `127.0.0.1:8765`.
- Sensitive API routes require a dedicated local bearer token.
- API callers cannot choose `user_id`; user scope comes from backend configuration.
- The Chrome extension only talks to the fixed localhost backend.
- The OpenAI API key stays out of the extension code and extension storage.
- Imports, queries, context output, archives, and PDF processing are bounded.
- Validation errors and general API errors are sanitized.
- Retrieved history is treated as untrusted evidence.
- Provenance is attached by trusted backend code rather than accepted from generated model output.
- Importing memory, retrieving memory, inserting context, submitting a ChatGPT message, and deleting stored memory are all separate user actions.

These protections are built for the local MVP.

The local bearer token is capability-style authentication. In-process rate limits are not durable. SQLite data and saved local credentials are not encrypted by Memora, and the loopback HTTP connection does not use TLS.

Do not expose the current backend configuration to a LAN or the public internet.

## Important residual risks

- Historical conversations and documents can contain indirect prompt injection. Memora uses bounded evidence, delimiters, synthesis isolation, and explicit user-controlled insertion to reduce this risk, but it cannot eliminate it completely.
- Anyone who gains access to the workstation, Chrome profile, local token, `.env`, database, exports, or backups may also gain access to sensitive Memora data.
- Deleting memory removes the configured user's active rows from the current database. It does not erase manual copies, backups, snapshots, provider-retained data, or text that was already inserted into ChatGPT.
- Changes to the ChatGPT DOM can break or alter extension behavior.
- Dependency scans and security checks describe the state of the project at the time they were run. They are not permanent guarantees.

A public or multi-user deployment would need a different security model, including production identity and session management, token rotation and revocation, TLS, explicit network policy, durable quotas, tenant isolation, managed secrets and encryption, backup and retention controls, operational monitoring, and a formal prompt-injection policy.

## Responsible disclosure

Please allow reasonable time to investigate and fix a reported issue before making it public.

Confirmed vulnerabilities may be documented through a GitHub security advisory after a fix is available.