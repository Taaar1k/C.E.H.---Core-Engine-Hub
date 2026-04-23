"""Command-line interface for C.E.H.

Minimal stub — all CLI commands have been removed.
The entry point remains for backward compatibility with pyproject.toml.
"""

import sys


def main() -> None:
    """Entry point for the `ceh` CLI.

    All commands have been removed. This is a no-op stub.
    """
    print("C.E.H. — Core Engine Hub (CLI removed)")
    print("This package is now a headless library.")
    print("Import via: from c_e_h.agent import Agent, AgentConfig")
    sys.exit(0)


if __name__ == "__main__":
    main()
