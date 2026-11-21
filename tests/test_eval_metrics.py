"""Eval metric unit tests — the math must be exactly right."""
from ai.evals.retrieval_metrics import (
    aggregate,
    hit_rate,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_precision_at_k():
    retrieved = ["a", "b", "c", "d", "e"]
    relevant = {"a", "c", "z"}
    assert precision_at_k(retrieved, relevant, 5) == 2 / 5
    assert precision_at_k(retrieved, relevant, 1) == 1.0


def test_recall_at_k():
    retrieved = ["a", "b", "c"]
    relevant = {"a", "c", "z"}
    assert recall_at_k(retrieved, relevant, 3) == 2 / 3
    assert recall_at_k(retrieved, set(), 3) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank(["x", "y", "a"], {"a"}) == 1 / 3
    assert reciprocal_rank(["a"], {"a"}) == 1.0
    assert reciprocal_rank(["x", "y"], {"a"}) == 0.0


def test_hit_rate():
    assert hit_rate(["x", "a"], {"a"}, 2) == 1.0
    assert hit_rate(["x", "a"], {"a"}, 1) == 0.0


def test_aggregate_averages():
    result = aggregate([{"m": 1.0}, {"m": 0.0}])
    assert result == {"m": 0.5}
    assert aggregate([]) == {}
