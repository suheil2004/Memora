# Memora

## One-Sentence Pitch

Memora is a personalized memory layer for AI that retrieves relevant context from your previous conversations.

## 30-Word Description

Memora gives ChatGPT continuity across conversations by semantically retrieving relevant history and letting users explicitly insert compact, attributed context into a new draft before manually submitting it to the assistant.

## 50-Word Description

Memora is a user-controlled memory layer for ChatGPT. It imports previous conversations, creates semantic embeddings, and retrieves the history relevant to a new question. A Chrome extension shows the matching conversation and lets the user explicitly insert compact context, while the local backend keeps API credentials out of the browser.

## 150-Word Description

Context is often fragmented across AI conversations: a technical setup described last week, a preference recorded in another thread, or a decision buried in a long history. Memora makes that context available without becoming another chatbot. Users explicitly import ChatGPT exports into a local FastAPI backend, where conversations are normalized, split into provenance-preserving chunks, embedded, and stored in SQLite. When a user writes a new question in ChatGPT and clicks **Retrieve Memory**, Memora embeds the query and uses semantic RAG to rank relevant historical chunks for that user. The Chrome extension presents the matching conversation and compact context. Nothing is inserted until the user clicks **Use This Context**, and Memora never automatically submits the message. OpenAI `text-embedding-3-small` powers semantic retrieval in the demo, while a deterministic local provider keeps tests offline. Memora adds continuity to an existing conversational AI assistant while preserving explicit control over retrieval, insertion, and final submission.

## The Problem

AI assistants are powerful, but relevant context can become fragmented or unavailable across separate conversations and tools. Users repeatedly explain projects, preferences, technical setups, earlier decisions, and personal context. Long threads make details hard to find, while fresh sessions often lack the history needed to interpret a short question.

## The Solution

Memora indexes conversations that the user explicitly imports, generates semantic embeddings, and retrieves only the historical chunks relevant to the current question. It surfaces attributed memory inside the existing ChatGPT experience. The user decides when retrieval happens, whether the context should enter the draft, and when to submit.

## How It Works

```text
ChatGPT History
  -> Import
  -> Chunk
  -> Embed
  -> Store
  -> Semantic Retrieval
  -> Relevant Memory
  -> Use This Context
```

## Key Features

- Semantic RAG over previous conversations
- Explicit ChatGPT JSON/ZIP history import and duplicate protection
- Manifest V3 Chrome extension with a ChatGPT adapter
- Explicit **Retrieve Memory** and **Use This Context** actions
- User-scoped search with conversation, chunk, and message provenance
- Compact, size-bounded context construction
- Local FastAPI and SQLite backend; no API key in the extension

## Why It Matters

Continuity makes an assistant more useful: a short question can refer to the user's real prior project rather than requiring another full explanation. Memora is not another chatbot. It is a memory layer that augments an existing assistant and keeps the user in control of when historical context is used.

## OpenAI Technology

OpenAI `text-embedding-3-small` generates semantic vectors for conversation chunks and user queries. Cosine similarity over those vectors powers retrieval of historically relevant discussions even when the new wording differs from the original. The embedding boundary is provider-independent, with a deterministic local implementation for development and testing. Codex was the primary engineering agent used throughout the project's iterative development.

## Retrieval Evaluation

| Provider | Top-1 | Top-3 |
| --- | ---: | ---: |
| Local feature-hash baseline | 46.7% | — |
| OpenAI `text-embedding-3-small` | 100% (15/15) | 100% (15/15) |

Measured on a small 15-query MVP evaluation set designed to test paraphrased retrieval across five conversation topics. These results validate the demo dataset and are not a production benchmark or a claim of universal accuracy.

## Built With Codex

Codex was used iteratively for repository scaffolding, the first end-to-end vertical slice, RAG and API integration, automated testing, TypeScript fixes, browser-extension debugging, documentation, and final hardening. Human direction defined the product scope, evaluated tradeoffs, supplied manual browser validation, and guided each iteration.

## Current MVP Limitations

- The FastAPI backend must run locally.
- The local bearer-token boundary is not production multi-user authentication.
- ChatGPT integration depends on non-public DOM selectors that may change.
- SQLite vector retrieval is a linear scan intended for demo-scale data.
- Large imports run synchronously.
- ChatGPT export formats may evolve.
- ChatGPT is the only implemented AI chat adapter.
- Structured durable-memory extraction is designed as a separate boundary but is not active.
- End-to-end encryption is not implemented.
- Memora does not automatically access ChatGPT history; users explicitly select supported export files.

## Future Direction

Possible next steps include additional AI-platform adapters, production authentication, encrypted storage, a scalable vector index, structured durable memory alongside raw-conversation RAG, and optional live conversation capture with explicit user permission. None of these are part of the current MVP.
