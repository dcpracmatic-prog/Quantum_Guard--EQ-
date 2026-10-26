import pytest
from eqg import score, select_layout


def test_selects_low_friction_connected_path():
    backend = {"friction": [0.8, 0.1, 0.2, 0.9], "edges": [(0, 1), (1, 2), (2, 3)]}
    assert select_layout(backend, 2) == [1, 2]


def test_layout_refuses_missing_connected_path():
    with pytest.raises(ValueError):
        select_layout({"friction": [0.1, 0.2, 0.3], "edges": [(0, 1)]}, 3)


def test_score_maxcut_path():
    result = score({"010": 4, "000": 2}, n=3)
    assert result["approximation_ratio"] == pytest.approx(2/3)
    assert result["standard_error"] >= 0


def test_score_rejects_empty_counts():
    with pytest.raises(ValueError):
        score({}, n=3)
