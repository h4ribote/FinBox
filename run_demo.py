"""Zero-config entry point for the walking-skeleton demo: ``python run_demo.py``.

Adds ``src/`` to the path so no install is required. Equivalent to
``pip install -e . && python -m finbox.demo``.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from finbox.demo import main  # noqa: E402

if __name__ == "__main__":
    main()
