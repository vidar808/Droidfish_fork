"""Pytest configuration for chess-uci-server tests.

Ensures the repository root (where chess.py lives) is on sys.path
so that ``import chess`` and ``import relay_server`` resolve correctly.
"""

import os
import sys

# Repository root contains the canonical chess.py and relay_server.py
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
