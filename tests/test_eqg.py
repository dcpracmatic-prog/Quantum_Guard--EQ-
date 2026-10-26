import pytest
from eqg import score, select_layout
from eqg.core import _result_counts


def test_selects_low_friction_connected_path():
    backend = {"friction": [0.8, 0.1, 0.2, 0.9], "edges": [(0, 1), (1, 2), (2, 3)]}
    assert select_layout(backend, 2) == [1, 2]


def test_layout_refuses_missing_connected_path():
    with pytest.raises(ValueError):
        select_layout({"friction": [0.1, 0.2, 0.3], "edges": [(0, 1)]}, 3)


def test_score_maxcut_path():
    result = score({"010": 4, "000": 2}, n=3)
    assert result["approximation_ratio"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("counts,n", [({}, 3), ({"01": -1, "10": 2}, 2), ({"abc": 1}, 3), ({"01": 1}, 3), ({"010": 1}, 1)])
def test_score_rejects_invalid_counts(counts, n):
    with pytest.raises(ValueError):
        score(counts, n)


def test_run_rejects_one_qubit_before_provider_import():
    from eqg import run
    class Circuit:
        num_qubits = 1
    with pytest.raises(ValueError, match="at least 2 qubits"):
        run(object(), Circuit(), 100)


def test_result_counts_reads_non_c_register_name():
    from types import SimpleNamespace
    class Bits:
        def get_counts(self):
            return {"01": 3}
    data = SimpleNamespace(meas=Bits())
    data.keys = lambda: ["meas"]
    assert _result_counts(SimpleNamespace(data=data)) == {"01": 3}


def test_bundled_config_disables_spending():
    from importlib.resources import files
    import yaml
    config = yaml.safe_load(files("eqg").joinpath("default.yaml").read_text())
    assert config["execution"]["confirm_spend"] is False
