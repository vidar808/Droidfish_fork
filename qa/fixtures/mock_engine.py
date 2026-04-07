"""Mock UCI chess engine for testing.

A minimal UCI-compliant engine that responds to standard UCI commands.
Can be run as a subprocess or used as a standalone script.

Usage:
    python mock_engine.py                  # normal mode
    python mock_engine.py --hang           # never sends uciok (for timeout tests)
    python mock_engine.py --crash          # exits after uci (for crash tests)
    python mock_engine.py --slow N         # delay N seconds before responding
"""

import sys
import time

ENGINE_NAME = "MockEngine"
ENGINE_AUTHOR = "QA Test Suite"


def main():
    hang = "--hang" in sys.argv
    crash = "--crash" in sys.argv
    slow = 0
    if "--slow" in sys.argv:
        idx = sys.argv.index("--slow")
        if idx + 1 < len(sys.argv):
            slow = float(sys.argv[idx + 1])

    current_position = "startpos"

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        if slow > 0:
            time.sleep(slow)

        if line == "uci":
            if crash:
                sys.exit(1)
            if hang:
                # Never respond - for timeout testing
                continue
            print(f"id name {ENGINE_NAME}")
            print(f"id author {ENGINE_AUTHOR}")
            print("option name Hash type spin default 16 min 1 max 1024")
            print("option name Threads type spin default 1 min 1 max 128")
            print("option name MultiPV type spin default 1 min 1 max 500")
            print("uciok")
            sys.stdout.flush()

        elif line == "isready":
            print("readyok")
            sys.stdout.flush()

        elif line.startswith("position"):
            current_position = line
            # No response needed

        elif line.startswith("go"):
            # Parse depth if given
            depth = 10
            parts = line.split()
            if "depth" in parts:
                idx = parts.index("depth")
                if idx + 1 < len(parts):
                    try:
                        depth = int(parts[idx + 1])
                    except ValueError:
                        pass

            # Emit a few info lines then bestmove
            for d in range(1, min(depth, 5) + 1):
                score = 30 + d * 5
                nodes = 1000 * d
                print(f"info depth {d} score cp {score} nodes {nodes} "
                      f"time {d * 10} pv e2e4 e7e5 g1f3")
                sys.stdout.flush()

            print("bestmove e2e4 ponder e7e5")
            sys.stdout.flush()

        elif line.startswith("setoption"):
            # Silently accept options
            pass

        elif line == "ucinewgame":
            current_position = "startpos"

        elif line == "stop":
            print("bestmove e2e4")
            sys.stdout.flush()

        elif line == "quit":
            break

    sys.exit(0)


if __name__ == "__main__":
    main()
