# API

The FastAPI application in `backend.api.app` exposes unauthenticated health plus authenticated conversation import/indexing and compact context retrieval. Sensitive routes require `Authorization: Bearer <MEMORA_LOCAL_TOKEN>` and derive their database scope from server-side `MEMORA_USER_ID`. Routes delegate to `MemoraService`; they do not duplicate RAG logic.
