"""Deterministic feature-hashed embeddings for demos and tests."""

import hashlib
import math
import re
from collections.abc import Sequence

from backend.interfaces import Embedding

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a", "an", "and", "are", "can", "for", "how", "i", "in", "is", "it",
    "my", "of", "on", "the", "to", "using", "what", "while", "with",
}


class LocalHashEmbeddingService:
    """Small local baseline; not a substitute for semantic production embeddings."""

    def __init__(self, dimensions: int = 1024) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self.dimensions = dimensions

    def embed_documents(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        return tuple(self._embed(text) for text in texts)

    def embed_query(self, text: str) -> Embedding:
        return self._embed(text)

    def _embed(self, text: str) -> Embedding:
        tokens = [_normalize(token) for token in _TOKEN_PATTERN.findall(text.lower())]
        tokens = [token for token in tokens if token and token not in _STOP_WORDS]
        features = tokens + [f"{left}_{right}" for left, right in zip(tokens, tokens[1:])]
        vector = [0.0] * self.dimensions
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return tuple(vector)


def _normalize(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) > len(suffix) + 3:
            return token[: -len(suffix)]
    return token
