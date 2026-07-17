# API

The FastAPI application in `backend.api.app` exposes health, conversation import/indexing, and compact context retrieval. Routes delegate to `MemoraService`; they do not duplicate RAG logic.
