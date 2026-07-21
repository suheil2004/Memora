# Memora

I built Memora around a problem I kept running into the more I used ChatGPT: the longer you use AI, the more useful context you build up, but the harder it becomes to actually use that context later.

You can spend months working on the same project across completely different conversations. One chat has the original idea. Another has a problem you ran into. A third has a decision you made, and then somewhere later you changed that decision completely. You might also have a PDF or attachment that mattered at the time but is now buried in your history.

Then you start a new conversation and basically none of that context is there.

That is the problem Memora is built for.

**The problem**

A normal conversation history is useful, but it is still just history. You have to remember where something was discussed, search for the right chat, read through old messages, and figure out which information is still current.

And even search by itself is not always enough.

Say you have been working on a drone detection project for six months. In an early conversation, you decided to use one design. A month later, you found a problem with it and switched to something else. If you ask about the project now, the most similar old message might still be the outdated one.

The point is not just to find text that looks similar.

The point is to find what from your history actually matters for what you are asking now.

**A memory layer you control**

Memora works alongside ChatGPT rather than replacing it.

You write your prompt like normal. Before sending it, you can ask Memora to retrieve relevant memory from the history you chose to import.

Memora searches through that history, finds the strongest related information, organizes it, and gives you clear MemoryBriefs instead of dumping raw old messages into the conversation.

You can see what each memory is about and where it came from.

Then you decide what happens next.

Nothing is silently inserted. Nothing is automatically sent. When you choose **Use This Context**, Memora adds the selected context to your draft so you can review it yourself before manually sending the message.

That control is one of the main ideas behind the product. I did not want Memora to act like an invisible memory system that decides on its own what ChatGPT should remember.

The user should be able to see the memory first.

**From conversation history to useful memory**

Finding a relevant old message is only the first step.

Memora tries to understand how the pieces of your history relate to each other before showing anything back to you.

If you are asking about one project, it should not mix in a completely different project just because both conversations happen to use similar technical words.

That is where **MemoryThreads** come in.

MemoryThreads keep related pieces of history together around the same subject, project, task, or goal. The idea is simple: one memory card should represent one coherent thing instead of blending unrelated parts of your history together.

Once Memora has found the right thread, it looks for the information inside it that actually matters for the current question.

These are **MemoryFacts**.

A MemoryFact might be a decision you made, a goal, a result, a constraint, a preference, a problem, a solution, a correction, or the current status of something you were working on.

They are created for the retrieval you are doing right now. Memora does not permanently store them as a separate hidden memory database.

This matters because the same conversation can be useful in different ways depending on what you ask.

If you ask, "What am I currently using for this project?" the latest correction might matter most.

If you ask, "What was my original design?" then the older information is exactly what you want.

Memora uses temporal reasoning to help with that distinction.

Newer is not automatically always better. Older is not automatically wrong either. The goal is to understand whether you are asking about the current state, the latest decision, or something historical.

After that, Memora turns the strongest information into **MemoryBriefs**.

These are the cards the user actually sees.

Instead of showing the internal retrieval process, each MemoryBrief gives you a clear summary of one relevant thread and keeps the source information attached so you can understand where it came from.

You should not have to trust a summary with no idea what it was based on.

**Moving between topics**

One thing I noticed while actually using Memora was that long results can create another small problem: once you scroll through several detailed memory cards, you should not have to scroll all the way back just to search for something else.

So the panel keeps the current search visible with **Showing memory for**.

When you change the prompt in ChatGPT, **Search current prompt** lets you run a new retrieval using whatever is currently written in the composer. The old cards are replaced with the new results instead of piling up underneath them.

**Clear results** removes the current cards and resets the view.

It does not delete your stored memory.

That distinction matters. Clearing what you are looking at should not mean deleting the history Memora remembers.

You can also switch between **Best match** and **Most recent** depending on whether you care more about relevance or recency.

**Memory beyond conversations**

Useful context is not always inside a chat message.

A project might depend on a PDF you uploaded months ago or an attachment that was part of an older ChatGPT conversation.

Memora can recover supported attachment information from imported ChatGPT history and index text PDFs when the original file can be resolved safely. Supported PDF content becomes searchable alongside conversation history, and the source can keep page-level provenance so the result still points back to where the information came from.

The goal is not to pretend every attachment can be understood.

When Memora cannot safely resolve the actual content of an attachment, it keeps the metadata rather than guessing what was inside.

**Designed around user control**

Memora separates every important action.

Importing history is one action.

Retrieving memory is another.

Choosing **Use This Context** is another.

Sending the final ChatGPT message is still your action.

Deleting stored memory is separate again.

That separation is intentional.

I wanted Memora to help with continuity without taking control away from the person using it.

The same idea applies when moving between searches. **Clear results** only clears the current result view. It does not delete stored conversations or documents.

For users who want to remove stored memory, those controls live separately in **Privacy & Memory**.

**Enhanced and Local modes**

Memora can run in two processing modes.

**Enhanced mode** uses configured OpenAI services for higher-quality semantic embeddings, MemoryFact extraction, and MemoryBrief synthesis.

**Local mode** runs without requiring an API key and uses the implemented local and deterministic processing path.

The experience is the same in the sense that you still retrieve memory, review it, and decide what to use, but the two modes do not promise identical retrieval or synthesis quality.

**More than similarity search**

A lot of retrieval systems are built around a simple question:

"What old text looks most similar to this query?"

That is useful, but it is not enough for the kind of memory I wanted Memora to provide.

Two conversations can use the same language and still be about different projects.

An old decision can be highly relevant while also being outdated.

The most important piece of context might be a correction you made later.

And sometimes what you need is not one old message at all, but the combination of a decision, a result, and the current status spread across multiple conversations.

Memora starts with retrieval, but the useful part comes from what happens after that: separating related history, identifying the facts that matter for the current question, understanding how information changed over time, turning it into clear MemoryBriefs, and preserving where that information came from.

The goal is not to remember everything.

It is to help find the right part of your history at the moment you actually need it, show it to you clearly, and let you decide whether it should become part of the conversation you are having now.