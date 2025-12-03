#!/usr/bin/env python3
"""PyInstaller entrypoint for the kubectl-a2a plugin binary.

This thin wrapper reuses the project CLI so that a frozen, single-file
binary can be built for distribution (e.g., for Krew-style tarballs).
"""

from src.cli import main


if __name__ == "__main__":
    main()
