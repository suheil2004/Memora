# Memora

**A memory layer for ChatGPT that helps you find what from your past conversations actually matters now.**

I built Memora because the longer I used ChatGPT, the more I kept running into the same problem.

You can spend months working on a project across dozens of conversations. Somewhere in that history is the original idea, a problem you ran into, a decision you made, a PDF you uploaded, and then maybe a correction you made three weeks later.

Then you start a new chat and basically none of that context is there.

You can search through old conversations, but similarity alone doesn't really solve the problem either. What happens when the most similar result contains a decision you already changed? Or when two completely different projects happen to use the same technical terms?

That is what I built Memora to handle.

Before sending a new prompt, you can ask Memora to look through your history and find what is relevant to what you're asking right now. Instead of dumping old messages into the conversation, it separates related topics, pulls out the decisions, results, corrections, constraints, and current status that matter, and turns them into clear MemoryBriefs.

You see where the information came from. You decide what to use. Nothing is silently inserted, and Memora never sends your ChatGPT message for you.

## See Memora in action

<img src="docs/assets/memora-panel.png" alt="Memora panel showing a sourced MemoryBrief" width="760">

*Memora turns relevant history into clear MemoryBriefs instead of making you dig through old conversations.*

<img src="docs/assets/memora-use-this-context.png" alt="Memora context inserted into the ChatGPT composer after explicit user selection" width="760">

*Choose **Use This Context** to bring a memory into your draft. You still review it and send the message yourself.*

<img src="docs/assets/memora-privacy-readiness.png" alt="Memora popup showing authenticated readiness and privacy controls" width="760">

*Your imported memory, readiness status, and memory controls are available from the extension.*

## What Memora does

- Imports the ChatGPT history you choose to give it, including supported attachments and recoverable text PDFs.
- Searches your history based on the prompt you're currently writing.
- Keeps different projects, subjects, tasks, and versions from getting mixed together through **MemoryThreads**.
- Pulls out useful information for the current question — things like decisions, goals, results, constraints, corrections, and current status — as query-time **MemoryFacts**.
- Pays attention to how information changed over time. If you changed a decision later, the older version shouldn't automatically win just because the wording happens to match better.
- Turns the strongest information into concise **MemoryBriefs** with provenance so you can see where it came from.
- Lets you switch between **Best match** and **Most recent**.
- Lets you move between topics with **Search current prompt** without scrolling through all of your previous results.
- Lets you **Clear results** without deleting any stored memory.
- Keeps **Use This Context** explicit. Memora never automatically sends anything to ChatGPT.

## How it works

Finding similar messages is only the first step.

Imagine you've been working on a drone detection project for six months. The model architecture is in one conversation, deployment is in another, and somewhere later you fixed a problem that made one of your earlier decisions obsolete.

A basic similarity search might bring back all of them.

Memora goes further.

```text
Your conversation history and supported PDFs
  → find relevant candidates
  → separate different subjects and projects into MemoryThreads
  → identify useful MemoryFacts for the current question
  → consider corrections and how information changed over time
  → create concise MemoryBriefs
  → show where the information came from
  → let you choose what to bring into ChatGPT
```

The point isn't to retrieve everything you've ever said.

It's to find **what from your history actually matters for what you're trying to do now**.

MemoryFacts are created for the current retrieval and are not permanently stored as a separate memory database.

## Why this is more than similarity search

Similarity helps. But it isn't the whole problem.

Two conversations can look similar while talking about completely different projects. An older message can be highly relevant while still being outdated. And sometimes the most important piece of context is a correction you made later, not the original discussion.

Memora combines semantic retrieval with additional ranking, topic separation, fact extraction, temporal reasoning, and provenance to make the result more useful.

The goal is not:

> "What old text looks most similar to this prompt?"

It's closer to:

> "What from this person's history actually matters for what they're asking right now?"

And even then, Memora doesn't silently decide what ChatGPT should remember. It shows the result to you first.

## Quick start

You need Windows PowerShell 5.1 or newer PowerShell, Python 3.11+, Node.js 20+ with npm, and Google Chrome.

From the root of the repository, run:

```powershell
.\start-memora.ps1
```

The first launch takes a little longer because Memora sets up the Python environment, installs anything that's missing, configures your processing mode, builds the extension, and starts the local backend.

Keep the launcher terminal open while you're using Memora. Closing it stops the backend.

Chrome requires a one-time unpacked extension installation from `extension/dist`.

See the [setup guide](docs/SETUP.md) for the full first-run process, importing your history, and troubleshooting.

## Full product overview

The [product overview](docs/PRODUCT.md) goes deeper into how Memora handles long-term conversation history, MemoryThreads, MemoryFacts, changing information, MemoryBriefs, provenance, and documents.

## Built with Codex and GPT-5.6

I built Memora through a combination of my own product decisions and iterative work with Codex and GPT-5.6.

**Codex** was used heavily inside the repository: implementing features, refactoring code, writing and running tests, debugging real failures, building the launcher, hardening security, and implementing extension UX.

**GPT-5.6** was used more as a reasoning and product-development partner. I used it to think through the memory architecture, challenge retrieval behavior, design MemoryThreads and MemoryFacts, reason about temporal ranking and corrections, debug problems, review security decisions, and iterate on the user experience.

They were tools used to build Memora, not substitutes for the product itself.

GPT-5.6 is not required to run Memora. Enhanced mode uses separately configured OpenAI services, while Local mode does not require an OpenAI API key.

## Testing

The automated test suite uses deterministic local implementations or mocked providers and does not call OpenAI.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall backend scripts tests

Set-Location extension
npm run test
npm run typecheck
npm run build
```

Latest verification:

- Backend tests: **101 passed**
- Extension tests: **78 passed**
- Python compilation: passed
- TypeScript strict typecheck: passed
- Production extension build: passed
- npm audit: **0 known vulnerabilities** at the time checked

## Security and privacy

Memora runs through a local backend and stores imported memory in the configured local SQLite database. Sensitive routes require a dedicated local authentication token, and Enhanced mode may send bounded text to the configured OpenAI provider.

Retrieval, inserting context, submitting a ChatGPT message, importing data, and deleting stored memory are all separate actions.

See [SECURITY.md](SECURITY.md) for the full security boundary and vulnerability reporting process.