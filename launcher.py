"""PyInstaller entry point for the packaged UI.

Uses absolute imports so the app can run both from source and from a frozen
single-file binary.
"""

import sys

from zkteco.ui.app import run_ui

if __name__ == "__main__":
    sys.exit(run_ui())
