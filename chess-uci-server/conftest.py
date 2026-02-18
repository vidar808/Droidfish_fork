"""Pytest configuration for chess-uci-server tests.

Handles the module-level config loading in chess.py by ensuring
tests can import from deploy/linux/ (where chess.py now lives).
"""

import os
import sys

# Ensure deploy/linux dir is on sys.path so `import chess` works
SERVER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deploy", "linux")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)
