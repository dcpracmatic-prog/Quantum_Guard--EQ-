from pathlib import Path
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from eqg_mvp.engine import morph_path, ar_from_counts, verdict


def test_morph_selects_connected_low_and_high_friction_paths():
    friction = [0.4, 0.1, 0.2, 0.3]
    edges = [[0, 1], [1, 2], [2, 3]]
    low = morph_path(4, friction, edges)
    high = morph_path(4, friction, edges, maximize=True)
    assert len(low) == 4 and len(set(low)) == 4
    assert len(high) == 4 and len(set(high)) == 4
    edge_set = {frozenset(e) for e in edges}
    assert all(frozenset(pair) in edge_set for pair in zip(low, low[1:]))
    assert all(frozenset(pair) in edge_set for pair in zip(high, high[1:]))
    assert sum(friction[q] for q in low) / 4 <= sum(friction[q] for q in high) / 4


def test_morph_fails_closed_when_no_path_exists():
    with pytest.raises(ValueError, match="no connected simple path"):
        morph_path(3, [0.1, 0.2, 0.3], [[0, 1]])


def test_ar_uses_path_maxcut_and_shot_uncertainty():
    ar, se = ar_from_counts({"0101": 100}, 4, 100)
    assert ar == pytest.approx(1.0)
    assert se == pytest.approx(0.0)
    ar, se = ar_from_counts({"0000": 50, "0101": 50}, 4, 100)
    assert ar == pytest.approx(0.5)
    assert se > 0


def test_verdict_gate_is_operational_contract_not_sim_runner_default():
    verdict_name, lower = verdict(.05, .01, 5, delta_min=.02, z_min=2, ic95_low_min=.006)
    assert verdict_name == "PRODUCTO_OK"
    assert lower == pytest.approx(.0304)
    assert verdict(-.01, .01, -1, delta_min=.02, z_min=2, ic95_low_min=.006)[0] == "NO_GO"


def test_cpu_fixture_is_explicitly_not_hardware_evidence():
    fixture = json.loads((ROOT / "tests/fixtures/mvp_cpu_backend.json").read_text())
    assert "not hardware calibration or evidence" in fixture["fixture_type"]
