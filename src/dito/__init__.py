"""Dito — ditado por voz offline."""

import os as _os

__version__ = "0.3.10"

# Before anything imports numpy: OpenBLAS reads these once, when it initialises. Its pool keeps
# spinning long after a 3 ms matmul ends — 15% of the CPU burned during transcription, and the
# log-mel is faster single-threaded anyway. See docs/armadilhas.md 3.9.
_os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
_os.environ.setdefault("OMP_NUM_THREADS", "1")
