"""What the frozen .exe runs: PyInstaller needs a script, and `__main__.py` imports relatively."""

from dito.cli import main

raise SystemExit(main())
