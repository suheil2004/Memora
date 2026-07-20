# Memora — Submission Description

## One-sentence pitch

Memora gives AI conversations continuity by finding the important current context in a user's history, preserving where it came from, and letting the user choose what to bring into a new chat.

## Problem

A fresh AI conversation often lacks the project decisions, preferences, constraints, corrections, and documents discussed in older chats. Nearest-text retrieval alone can surface outdated versions or blend distinct subjects, while silently injecting history removes user awareness and control.

## What Memora does

Memora explicitly imports supported ChatGPT history and recoverable attachment assets into a local FastAPI/SQLite service. It retrieves relevant conversation and PDF evidence, organizes it into distinct memories, identifies important facts, reasons about current versus historical state, and presents concise sourced MemoryBriefs inside ChatGPT.

The user decides when retrieval happens, which brief to insert with **Use This Context**, and when to submit. Memora does not automatically access account history, inject all retrieved context, or press Send.

## Why it is different

Basic semantic RAG typically follows `query → nearest chunks → prompt`. Memora follows:

`query → eligible evidence → hybrid reranking/entity scope → MemoryThreads → query-time MemoryFacts → salience/specificity/temporal ranking → per-thread MemoryBriefs → trusted sources → user-selected insertion`

This separates different subjects and versions before synthesis, favors explicit current-state and correction evidence when the question calls for it, preserves old versions for historical questions, and attaches provenance in backend code rather than trusting generated citations.

## How it works

- ChatGPT JSON/ZIP conversations are normalized and split into role-aware, provenance-preserving chunks.
- Safely resolved historical text PDFs can be recovered automatically and indexed with page sources; ambiguous assets remain metadata-only.
- OpenAI `text-embedding-3-small` supplies semantic candidates for the demo, with a deterministic local implementation for offline tests.
- Hybrid reranking and exact entity/course boundaries improve precision before conservative MemoryThread grouping.
- Active query-time MemoryFact extraction removes filler and ranks facts by query utility, salience, specificity, corrections, trusted timestamps, and current/historical intent. These facts are ephemeral; durable persisted MemoryFacts are not implemented.
- Each selected thread becomes one bounded MemoryBrief. Trusted conversations, documents, pages, and timestamps are attached by Memora after model output.
- A Manifest V3 extension displays up to five cards with **Best match / Most recent** sorting and explicit context insertion.

## Privacy and user control

Imported history, embeddings, recovered document text, and provenance are stored in the configured local database. When OpenAI providers are enabled, bounded text may be sent for embeddings, MemoryFact extraction, and MemoryBrief synthesis; API credentials remain in the backend process.

Sensitive API operations require a dedicated localhost bearer token and server-derived user scope. Historical content is treated as untrusted evidence, rendered safely, and inserted only after an explicit click. The popup exposes authenticated aggregate counts and two-step clearing of active Memora records. Manual backups and context already inserted into ChatGPT are not deleted.

## Technical depth and evidence

The implemented system includes conservative ChatGPT graph import, duplicate replacement, automatic attachment/PDF recovery, compatible-vector enforcement, semantic abstention, entity/course scoping, hybrid reranking, thread separation, fact extraction, correction handling, temporal ranking, resilient structured synthesis, trusted provenance, runtime-message validation, explicit insertion, and privacy controls.

Current verification is **101/101 backend tests**, **72/72 extension tests**, Python compilation, strict TypeScript typecheck, and production extension build. Automated tests use deterministic local or mocked providers and do not call OpenAI.

The repository's small semantic retrieval fixture previously measured OpenAI embeddings at 15/15 positive Top-1 and Top-3; the local feature-hash baseline measured 46.7% positive Top-1 and 5/5 negative abstention. These are semantic retrieval results, not a comparative benchmark for the full memory-intelligence pipeline. Reranking and end-to-end behavior are validated separately by deterministic tests.

## Demo

In a fresh ChatGPT conversation, ask about a project with an old and current design. Click **Retrieve Memory** to show the current-state brief first, a historical memory separately, trusted chat/PDF page sources, and timestamps. Select **Use This Context** to insert one bounded brief while preserving the original question. Review and submit manually.

The hackathon MVP is developer-operated: it requires a local FastAPI service, unpacked Chrome extension, environment configuration, and supported provider setup. It is not yet consumer-packaged, production multi-user, encrypted at rest, or designed for large vector indexes. ChatGPT DOM changes may require adapter maintenance, query-time fact/synthesis calls add latency, prompt-injection risk cannot be eliminated, and not every historical attachment is recoverable.

## Built with Codex

Codex supported iterative scaffolding, implementation, testing, browser debugging, security hardening, and documentation. Human direction defined product scope, evaluated tradeoffs, and validated the demo.
