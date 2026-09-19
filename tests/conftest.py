"""Garante repo root no sys.path para `pytest tests/` sem PYTHONPATH."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
