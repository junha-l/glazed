#!/usr/bin/env python
"""Run from a source checkout without installing, e.g. under Blender's own Python:

    blender -b -P render.py -- examples/donut.npy

Once installed (pip install .), use the `glazed` command instead.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from glazed.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
