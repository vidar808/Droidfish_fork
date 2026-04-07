#!/bin/bash
# Stop the Chess UCI Server
cd "$(dirname "$0")"
python3 chess.py --stop
