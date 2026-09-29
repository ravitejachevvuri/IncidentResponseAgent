"""Lightweight deterministic text embeddings.

We don't want to depend on downloading a large sentence-transformer
model at build/demo time (no guaranteed network access, no guaranteed GPU).
Instead we hash symptom/root-cause text into a fixed-size bag-of-words vector.
This is enough to demonstrate the vector-similarity retrieval path end-to-end;
the authoritative similarity/confidence signal is the structured scorer in
services/similarity_service.py.
"""
import hashlib
import math
import re

VECTOR_DIM = 64


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def embed_text(text: str) -> list[float]:
    vector = [0.0] * VECTOR_DIM
    for token in _tokens(text):
        idx = int(hashlib.sha256(token.encode()).hexdigest(), 16) % VECTOR_DIM
        vector[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def embed_incident(symptoms: list[str], root_cause: str | None) -> list[float]:
    return embed_text(" ".join(symptoms) + " " + (root_cause or ""))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return max(0.0, min(1.0, dot))
