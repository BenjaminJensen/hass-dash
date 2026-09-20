"""PLAN.md M8.2, and AGENTS.md's rule that this container has no hardware.

> Do not assume GPIO, SPI, or e-paper hardware access works inside the
> container.

Importing a pin configuration is not a statement that hardware exists - it is
a claim on it. The vendored `epdconfig` imports `gpiozero` and `spidev` at the
top, and `epd7in5b_V2` goes further: it does `epdconfig = RaspberryPi()` at
module scope, and that constructor takes four GPIO pins (HARDWARE.md
section 5). On the Pi, an accidental import at collection time would take the
pins away from the running dashboard; in the container it is an `ImportError`
that would turn one milestone's module into a suite-wide collection failure.

So the rule is: **one module may name the hardware libraries, and only inside
a constructor.** Since PLAN.md M10 that module is `render/panel/transport.py`,
where the claim is made by `SpiTransport()` rather than by an import, and the
one place that constructs one is `render.epd.open_panel()`. The vendored
driver is now named by nothing in `src/` at all - it survives as the reference
the transcripts in `tests/fixtures/transcripts/` were recorded from, imported
only inside `tests/panel_harness.py`'s fixture.

This file asserts it from three sides - the source tree, the test tree, and a
real interpreter that imports the composition root and looks at what came with
it.

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

#: The libraries themselves, as opposed to the vendored modules that wrap
#: them. The gateway may name these; nothing may name the vendored pair.
LIBRARIES = frozenset({"gpiozero", "spidev"})

#: The one module allowed to reach them, and only from inside a constructor.
GATEWAY = "render/panel/transport.py"

#: The one place allowed to construct the gateway, so that the claim on the
#: pins happens at a known line rather than wherever an import lands.
OPENER = "render/epd.py"

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
            "GPIO and SPI are claimed on import; they belong inside "
            f"{GATEWAY}'s constructor."
        )

    @pytest.mark.parametrize("path", application_modules(), ids=lambda p: p.name)
    def test_only_the_gateway_names_the_libraries_at_all(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        reached = sorted(any_imports(tree) & HARDWARE)

        if path.relative_to(SRC).as_posix() == GATEWAY:
            assert set(reached) <= LIBRARIES, f"{GATEWAY} imports {reached}"
            return

        assert reached == [], f"{path.relative_to(SRC)} imports {reached}"

    def test_the_gateway_claims_the_pins_in_its_constructor(self):
        """The import is the claim, so it happens where the claim is wanted -
        and the module stays importable in a container that has neither
        library, which is what lets `--target epd` be built anywhere."""
        source = (SRC / GATEWAY).read_text(encoding="utf-8")
        tree = ast.parse(source)

        assert module_scope_imports(tree) & HARDWARE == set()
        assert any_imports(tree) & HARDWARE == LIBRARIES

        constructor = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "__init__"
        )
        assert any_imports(constructor) & HARDWARE == LIBRARIES

    def test_the_vendored_driver_is_named_by_nothing_in_src(self):
        """PLAN.md M10.5. It stays in the tree as the reference the transcripts
        were recorded from and the only way to re-record, but nothing in the
        application reaches it any more - `tests/panel_harness.py` is the only
        importer, and it does that inside a fixture."""
        for path in application_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            named = sorted(any_imports(tree) & {"epdconfig", "epd7in5b_V2"})

            assert named == [], f"{path.relative_to(SRC)} imports {named}"

    def test_one_module_constructs_the_gateway(self):
        """So the claim on the pins is one line in one file, rather than
        wherever a transport happens to be built."""
        builders = [
            path.relative_to(SRC).as_posix()
            for path in application_modules()
            if "SpiTransport" in path.read_text(encoding="utf-8")
            and path.relative_to(SRC).as_posix() != GATEWAY
        ]

        assert builders == [OPENER]


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

    def test_importing_the_gateway_itself_touches_no_hardware(self):
        """The strongest form of M10.2's claim: the module that owns the pins
        can be imported on a machine that has none. Constructing it is what
        fails, and `tests/test_panel_transport.py` shows it failing."""
        assert self.imports("from render.panel.transport import SpiTransport") == set()

    def test_importing_the_driver_touches_no_hardware(self):
        """Every command sequence in `render/panel/driver.py` is asserted in
        this container, which is only possible because the driver takes its
        transport as an argument."""
        assert self.imports("from render.panel.driver import Panel") == set()
