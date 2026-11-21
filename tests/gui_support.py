"""Optional GUI dependency checks shared by unittest and pytest modules."""

from importlib.util import find_spec
from unittest import SkipTest


def require_gui():
    """Skip the importing module under either runner if GUI extras are absent."""
    if any(find_spec(module) is None for module in ("PySide6", "pyqtgraph")):
        raise SkipTest("PySide6 and pyqtgraph are needed for GUI tests")
