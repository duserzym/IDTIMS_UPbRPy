"""Guards against Studio's frozen-only import bugs, for both packages.

1. No module defines a module-level `__getattr__` (a lazy attribute hook that
   raised ImportError broke Studio only inside PyInstaller).
2. Every module imports, and every public name is imported explicitly with
   `from <module> import <name>`, the way frozen code reaches them.

The idtims_app modules that need Qt are skipped when PySide6 is missing.
"""
import ast
import importlib.util
import pkgutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
QT_FREE_APP_MODULES = {"idtims_app", "idtims_app.branding", "idtims_app.steps",
                       "idtims_app.services", "idtims_app.verification",
                       "idtims_app.reduction", "idtims_app.review", "idtims_app.project",
                       "idtims_app.autosave", "idtims_app.reporting"}
HAS_QT = importlib.util.find_spec("PySide6") is not None and \
    importlib.util.find_spec("pyqtgraph") is not None


def _modules(package):
    names = [package]
    path = SRC / package
    for info in pkgutil.walk_packages([str(path)], prefix=package + "."):
        names.append(info.name)
    return sorted(names)


ENGINE = _modules("IDTIMS_UPbRPy")
APP = _modules("idtims_app")


def _source(module):
    relative = Path(*module.split("."))
    package_init = SRC / relative / "__init__.py"
    return package_init if package_init.exists() else SRC / relative.with_suffix(".py")


@pytest.mark.parametrize("module", ENGINE + APP)
def test_no_module_level_getattr(module):
    tree = ast.parse(_source(module).read_text(encoding="utf-8"))
    hooks = [node.name for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in ("__getattr__", "__dir__")]
    assert hooks == [], f"{module} defines {hooks}; keep imports eager"


def _public_names(module_object):
    names = getattr(module_object, "__all__", None)
    if names is None:
        names = [n for n, v in vars(module_object).items() if not n.startswith("_")
                 and getattr(v, "__module__", module_object.__name__) == module_object.__name__]
    return sorted(names)


def _check_imports(module):
    namespace = {}
    exec(f"import {module} as target", namespace)
    for name in _public_names(namespace["target"]):
        exec(f"from {module} import {name}", namespace)
        assert name in namespace, f"{module}.{name}"


@pytest.mark.parametrize("module", ENGINE)
def test_engine_public_names_import(module):
    _check_imports(module)


@pytest.mark.parametrize("module", APP)
def test_app_public_names_import(module):
    if module not in QT_FREE_APP_MODULES and not HAS_QT:
        pytest.skip("needs the gui extra (PySide6, pyqtgraph)")
    _check_imports(module)


def test_both_packages_found():
    assert "IDTIMS_UPbRPy.fractions" in ENGINE
    assert {"idtims_app.main", "idtims_app.window", "idtims_app.ui.theme"} <= set(APP)
