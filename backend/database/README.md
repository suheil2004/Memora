# Database

`SQLiteVectorStore` persists chunks, vectors, provider/model metadata, and import fingerprints. Search and replacement are scoped by `user_id`; cosine ranking is a linear scan suitable for the local MVP.
