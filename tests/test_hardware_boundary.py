"""PLAN.md M8.2, and AGENTS.md's rule that this container has no hardware.

> Do not assume GPIO, SPI, or e-paper hardware access works inside the
> container.

Importing `epdconfig` is not a statement that hardware exists - it is a claim
on it. The module imports `gpiozero` and `spidev` at the top, and
`epd7in5b_V2` goes further: it does `epdconfig = RaspberryPi()` at module
scope, and that constructor takes five GPIO pins and opens an SPI device. On
the Pi, an accidental import at collection time would take the pins away from
the running dashboard; in the container it is an `ImportError` that would turn
one milestone's module into a suite-wide collection failure.

So the rule is: **the import happens inside `render.epd.open_panel()` and
nowhere else.** This file asserts it from three sides - the source tree, the
test tree, and a real interpreter that imports the composition root and looks
at what came with it.

The sibling of `test_source_boundary.py`: same argument, different boundary.
One keeps Home Assistant's vocabulary below the adapter; this one keeps the
panel's electricity below one function.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
TESTS = Path(__file__).parent

#: The vendored driver and its pin configuration. Between them they are the
#: only two modules in the repository that may touch GPIO or SPI at import.
HARDWARE = frozenset({"epdconfig", "epd7in5b_V2", "gpiozero", "spidev"})

#: The one module allowed to reach them, and only from inside a function.
GATEWAY = "render/epd.py"

#: The vendored files themselves, which import each other by design. Named
#: individually rather than skipped by a pattern, so that a third file cannot
#: quietly inherit the exemption.
VENDORED = frozenset({"epdconfig.py", "epd7in5b_V2.py"})


def module_scope_imports(tree: ast.AST) -> set[str]:
    """Top-level package names imported where the import statement runs at
    import time - module scope and class bodies, not function bodies."""
    found: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
    return found


def any_imports(tree: ast.AST) -> set[str]:
    """Everything a module imports, wherever the statement sits."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
    return found


def application_modules() -> list[Path]:
    return [
        path
        for path in sorted(SRC.rglob("*.py"))
        if path.relative_to(SRC).as_posix() not in VENDORED
    ]


def suite_modules() -> list[Path]:
    return sorted(TESTS.rglob("test_*.py"))


class TestTheSourceTree:
    def test_there_is_something_to_check(self):
        assert len(application_modules()) >= 20

    @pytest.mark.parametrize("path", application_modules(), ids=lambda p: p.name)
    def test_no_module_pulls_in_hardware_at_import_time(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        leaked = sorted(module_scope_imports(tree) & HARDWARE)

        assert leaked == [], (
            f"{path.relative_to(SRC)} imports {leaked} at module scope. "
            "The driver claims GPIO pins on import; it belongs inside "
            "render.epd.open_panel()."
        )

    @pytest.mark.parametrize("path", application_modules(), ids=lambda p: p.name)
    def test_only_the_gateway_names_the_driver_at_all(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        reached = sorted(any_imports(tree) & HARDWARE)

        if path.relative_to(SRC).as_posix() == GATEWAY:
            return

        assert reached == [], f"{path.relative_to(SRC)} imports {reached}"

    def test_the_gateway_reaches_the_driver_dynamically(self):
        """`importlib` rather than an `import` statement, so that the name is a
        string the AST scan above cannot mistake for a dependency - and so the
        driver is loaded on the first frame rather than on the first import."""
        source = (SRC / GATEWAY).read_text(encoding="utf-8")
        tree = ast.parse(source)

        assert module_scope_imports(tree) & HARDWARE == set()
        assert "importlib" in any_imports(tree)
        assert "epd7in5b_V2" in source


class TestTheTestTree:
    def test_there_is_something_to_check(self):
        assert len(suite_modules()) >= 10

    @pytest.mark.parametrize("path", suite_modules(), ids=lambda p: p.name)
    def test_no_test_module_pulls_in_hardware_at_import_time(self, path):
        """PLAN.md M8.2, stated exactly: nothing under `tests/` may pull
        `epdconfig` in at module scope. Collection imports every one of these
        before a single test runs, so one stray import fails the whole suite on
        a machine without `gpiozero`."""
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        leaked = sorted(module_scope_imports(tree) & HARDWARE)

        assert leaked == [], f"tests/{path.name} imports {leaked} at module scope"


class TestARealInterpreter:
    """The scans above read code. This one runs it."""

    @staticmethod
    def imports(statement: str) -> set[str]:
        """What is in `sys.modules` after a fresh interpreter runs one line."""
        program = (
            "import sys; "
            f"sys.path.insert(0, {str(SRC)!r}); "
            f"{statement}; "
            "print(' '.join(sorted(set(sys.modules) & "
            f"{set(HARDWARE)!r})))"
        )
        done = subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(ROOT),
        )
        return set(done.stdout.split())

    def test_importing_the_composition_root_touches_no_hardware(self):
        assert self.imports("import app") == set()

    def test_importing_the_panel_target_touches_no_hardware(self):
        """Building `--target epd` inside the container has to work; only
        driving it may fail."""
        assert self.imports("from render.epd import EPDRenderer; EPDRenderer()") == set()
