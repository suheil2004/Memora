"""Explainable MVP relevance thresholds for supported embedding spaces."""

import os

from backend.interfaces import EmbeddingService


class RelevanceConfigurationError(ValueError):
    """The active embedding space has no calibrated relevance floor."""


def minimum_relevance_similarity(embeddings: EmbeddingService) -> float:
    """Return the calibrated cosine floor for the active embedding provider."""
    configured = os.environ.get("MEMORA_RELEVANCE_MIN_SIMILARITY")
    if configured is not None and configured.strip():
        try:
            threshold = float(configured)
        except ValueError as exc:
            raise RelevanceConfigurationError(
                "MEMORA_RELEVANCE_MIN_SIMILARITY must be a number between -1 and 1"
            ) from exc
        if not -1.0 <= threshold <= 1.0:
            raise RelevanceConfigurationError(
                "MEMORA_RELEVANCE_MIN_SIMILARITY must be between -1 and 1"
            )
        return threshold
    if embeddings.provider_name == "local":
        return 0.06 if embeddings.model_name == "feature-hash-v1-1024" else 0.08
    raise RelevanceConfigurationError(
        "MEMORA_RELEVANCE_MIN_SIMILARITY must be configured for "
        f"{embeddings.provider_name}/{embeddings.model_name} after calibration"
    )
