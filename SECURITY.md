# Security Policy

## Supported Versions

Memora is currently an active MVP and hackathon project. Security updates are applied to the latest version of the codebase.

| Version | Supported |
| ------- | --------- |
| Latest code on `main` | ✅ |
| Older commits or releases | ❌ |

## Reporting a Vulnerability

If you discover a security vulnerability in Memora, please report it privately using GitHub's **Private Vulnerability Reporting** feature for this repository.

Please do not open a public GitHub issue containing sensitive vulnerability details, proof-of-concept exploits, API keys, tokens, private user data, or other confidential information.

When submitting a report, please include:

- A clear description of the vulnerability
- The affected component or feature
- Steps to reproduce the issue
- The potential security impact
- Any suggested remediation, if known

I will review security reports as soon as reasonably possible and aim to provide an initial response within 5 business days.

If the vulnerability is confirmed, I will work to address the issue and may publish a security advisory once an appropriate fix is available.

If a report is determined not to represent a security vulnerability, I will provide an explanation where possible.

## Security Scope

Memora is currently designed as a local-first MVP using a Chrome extension and a backend bound to `127.0.0.1`.

The current MVP should not be treated as production-ready for public or multi-user deployment without additional security controls, including production authentication, encrypted storage and key management, TLS, durable rate limiting, tenant isolation, and operational monitoring.

## Responsible Disclosure

Please allow reasonable time for a confirmed vulnerability to be investigated and addressed before publicly disclosing technical details.
