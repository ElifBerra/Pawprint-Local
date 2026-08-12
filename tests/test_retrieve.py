"""Tests for retrieval and the relevance threshold.

The embedding model is stubbed out, so these run without loading anything.
That is the reason get_top_chunks accepts a chunks argument.
"""

import numpy as np
import pytest

from src import config, retrieve
from src.models import Chunk, Retrieved


def vec(*values) -> np.ndarray:
    return np.asarray(values, dtype=np.float32)


@pytest.fixture
def chunks():
    return [
        Chunk(source="a.md", chunk_index=0, content="alpha", embedding=vec(1, 0, 0)),
        Chunk(source="b.md", chunk_index=0, content="beta", embedding=vec(0, 1, 0)),
        Chunk(source="c.md", chunk_index=0, content="gamma", embedding=vec(0, 0, 1)),
    ]


@pytest.fixture(autouse=True)
def clear_query_cache():
    retrieve._query_cache.clear()
    yield
    retrieve._query_cache.clear()


def test_rank_orders_by_similarity(chunks):
    results = retrieve.rank(vec(0.9, 0.1, 0), chunks)
    assert [r.chunk.source for r in results] == ["a.md", "b.md", "c.md"]
    assert results[0].score > results[1].score > results[2].score


def test_rank_returns_every_chunk(chunks):
    assert len(retrieve.rank(vec(1, 0, 0), chunks)) == len(chunks)


def test_rank_on_empty_input():
    assert retrieve.rank(vec(1, 0, 0), []) == []


def test_identical_vectors_score_close_to_one(chunks):
    results = retrieve.rank(vec(1, 0, 0), chunks)
    assert results[0].score == pytest.approx(1.0, abs=1e-5)


def test_orthogonal_vectors_score_near_zero(chunks):
    results = retrieve.rank(vec(1, 0, 0), chunks)
    assert results[-1].score == pytest.approx(0.0, abs=1e-5)


def test_get_top_chunks_respects_k(monkeypatch, chunks):
    monkeypatch.setattr(retrieve, "embed_query", lambda q: vec(1, 0, 0))
    assert len(retrieve.get_top_chunks("anything", k=2, chunks=chunks)) == 2


def test_get_top_chunks_on_blank_query(chunks):
    assert retrieve.get_top_chunks("", chunks=chunks) == []
    assert retrieve.get_top_chunks("   ", chunks=chunks) == []


def test_get_top_chunks_with_no_stored_chunks(monkeypatch):
    monkeypatch.setattr(retrieve, "embed_query", lambda q: vec(1, 0, 0))
    assert retrieve.get_top_chunks("anything", chunks=[]) == []


def test_query_vector_is_cached(monkeypatch):
    calls = []

    def fake_embed_one(text):
        calls.append(text)
        return vec(1, 0, 0)

    monkeypatch.setattr(retrieve.embeddings, "embed_one", fake_embed_one)

    retrieve.embed_query("How often do I feed a kitten?")
    retrieve.embed_query("how often do I FEED a kitten?   ")

    # Same question, different case and spacing: one embedding call.
    assert len(calls) == 1


def test_is_relevant_uses_the_threshold(chunks):
    above = [Retrieved(chunk=chunks[0], score=config.SIM_THRESHOLD + 0.01)]
    below = [Retrieved(chunk=chunks[0], score=config.SIM_THRESHOLD - 0.01)]

    assert retrieve.is_relevant(above)
    assert not retrieve.is_relevant(below)


def test_is_relevant_on_empty_results():
    assert not retrieve.is_relevant([])


def test_is_relevant_only_looks_at_the_best_match(chunks):
    # A strong first hit carries the decision even if later ones are weak.
    results = [
        Retrieved(chunk=chunks[0], score=0.9),
        Retrieved(chunk=chunks[1], score=0.01),
    ]
    assert retrieve.is_relevant(results)
