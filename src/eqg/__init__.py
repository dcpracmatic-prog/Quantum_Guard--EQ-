"""EQG selects a low-friction qubit layout, executes a workload, and scores results."""
from .core import run, score, select_layout, validate

__all__ = ["select_layout", "run", "validate", "score"]
__version__ = "0.1.0"
