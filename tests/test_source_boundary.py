"""INTENT.md section 2, enforced by a test rather than by discipline.

> Home Assistant is a source, not a foundation. HA is generous and unstable -
> entity ids get renamed, attribute shapes change between releases, the
> forecast API has already moved once. Nothing above the adapter layer may know
> that Home Assistant exists.

That rule is only worth writing down if something checks it. A leak is easy and
invisible: a view function that reaches for `snapshot.rooms[0].entity_id`
because it happens to be there, a refresh policy keyed on `hvac_action`. Each
one is small, and together they are how an adapter layer stops being a
boundary.

**This reads code, not text.** The scan walks the AST, so a docstring saying
"no Home Assistant vocabulary" - as `domain/models.py` does - is not a
violation, while `getattr(x, "entity_id")` is.

`config/` is exempt because mapping rooms to entity ids is what configuration
*is* (INTENT.md section 6), and nothing it exposes reaches `domain/` or above.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"

#: Allowed to know. The source layer by definition, and the configuration,
#: which is where entity ids are written down.
EXEMPT_PACKAGES = ("sources", "config")

#: The composition root, which is scanned by its own narrower rule below.
#: `app.py` has to import `sources/` and name the adapter it is building -
#: that is what composing means - and no other module in the project does.
COMPOSITION_ROOT = "app.py"

#: The only two words the composition root may use that the rest of the code
#: may not. It may *name* the adapter; it may not *speak* its language, so
#: `entity_id`, `current_humidity` and the rest of FORBIDDEN still apply to it.
ROOT_MAY_NAME = frozenset({"homeassistant", "hass"})

#: The widget layer, the retired HA client and the vendored panel driver. These
#: are dead code walking: PLAN.md M11 deletes `components/`, `core/`,
#: `dashboard.py`, `localize.py` and `rendering/` once the new screen is on the
#: wall. They are listed individually rather than skipped by a pattern so that
#: deleting one makes this list shrink, and adding a file to one of them does
#: not quietly inherit an exemption.
LEGACY = (
    "components/__init__.py",
    "components/rooms_widget.py",
    "components/sun_widget.py",
    "components/weather_forecast_widget.py",
    "components/weather_icons.py",
    "components/weather_widget.py",
    "components/widget.py",
    "core/__init__.py",
    "core/hass_client.py",
    "core/hass_mock.py",
    "dashboard.py",
    "localize.py",
    "rendering/__init__.py",
    "rendering/renderer.py",
    # Vendored Waveshare driver and its pin configuration, kept verbatim so
    # upstream fixes can be diffed in. PLAN.md M10 replaces them as the code
    # that runs and keeps them here as the reference it is proven against.
    "epd7in5b_V2.py",
    "epdconfig.py",
)

#: Home Assistant's vocabulary. If one of these appears in code above the
#: boundary, something has leaked.
FORBIDDEN = frozenset(
    {
        "homeassistant",
        "homeassistant_api",
        "hass",
        "entity_id",
        "entity_ids",
        "hvac_action",
        "hvac_modes",
        "current_temperature",
        "current_humidity",
        "templow",
        "unavailable",
        "above_horizon",
        "below_horizon",
        "service_response",
        "get_forecasts",
        "friendly_name",
        "device_class",
        "state_class",
        "unit_of_measurement",
        "last_changed",
        "attributes",
    }
)


def modules() -> list[Path]:
    """Every application module that is meant to be free of HA vocabulary."""
    found = []
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC)
        if relative.parts[0] in EXEMPT_PACKAGES or relative.as_posix() in LEGACY:
            continue
        if relative.as_posix() == COMPOSITION_ROOT:
            continue
        found.append(path)
    return found


def _imports(tree: ast.AST) -> set[str]:
    """The top-level package name of everything a module imports."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
    return found


def identifiers(tree: ast.AST) -> set[str]:
    """Every name this module actually uses, ignoring comments and docstrings.

    Docstrings are skipped deliberately: `domain/models.py` says in prose that
    it holds "no Home Assistant vocabulary", and a grep-based version of this
    test would call that a violation. Explaining the boundary is not crossing
    it.
    """
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            used.add(node.arg)
        elif isinstance(node, ast.arg):
            used.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            used.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                used.update(node.module.split("."))
            for alias in node.names:
                used.update(alias.name.split("."))
                if alias.asname:
                    used.add(alias.asname)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node not in docstrings:
                used.add(node.value)

    return used


class TestNoHomeAssistantAboveTheBoundary:
    def test_there_is_something_to_check(self):
        """Guards against the scan silently matching nothing and passing."""
        assert len(modules()) >= 4

    @pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
    def test_module_is_free_of_home_assistant_vocabulary(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        leaked = sorted(name for name in identifiers(tree) if name.lower().strip() in FORBIDDEN)

        assert leaked == [], (
            f"{path.relative_to(SRC)} uses Home Assistant vocabulary {leaked}. "
            "Only sources/ and config/ may know HA exists (INTENT.md section 2)."
        )

    @pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
    def test_module_does_not_import_the_source_layer(self, path):
        """Domain and everything above it must not reach down into sources/.

        Data flows upward - a source builds a `Snapshot` and hands it over. A
        domain module importing `sources` would invert that and make the
        boundary decorative.
        """
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        assert "sources" not in _imports(tree), f"{path.relative_to(SRC)} imports sources/"


class TestTheCompositionRoot:
    """`app.py` gets an exemption, and it is deliberately a narrow one.

    A composition root selects concrete implementations; that is its entire
    job, and INTENT.md section 6 puts it at the top of the diagram for exactly
    that reason. It therefore has to import `sources/` and it has to be able to
    write `--source hass` on a command line. What it must *not* do is read one
    of Home Assistant's fields: the moment `app.py` knows what an `entity_id`
    is, the adapter layer has stopped being a boundary and has become a
    suggestion.

    So the exemption is two words wide - the names of the thing being built -
    and every other piece of HA vocabulary still applies.
    """

    @staticmethod
    def root() -> Path:
        return SRC / COMPOSITION_ROOT

    def test_the_exemption_is_two_words_and_not_a_free_pass(self):
        """If this ever grows, it is a boundary decision, not a typo."""
        assert ROOT_MAY_NAME < FORBIDDEN
        assert len(ROOT_MAY_NAME) == 2

    def test_it_may_name_the_adapter_but_not_speak_its_language(self):
        tree = ast.parse(self.root().read_text(encoding="utf-8"), filename=str(self.root()))
        vocabulary = FORBIDDEN - ROOT_MAY_NAME
        leaked = sorted(name for name in identifiers(tree) if name.lower().strip() in vocabulary)

        assert leaked == [], (
            f"app.py uses Home Assistant vocabulary {leaked}. The composition root may "
            "name the adapter it builds; it may not read Home Assistant's fields."
        )

    def test_it_is_the_only_module_allowed_to_import_the_source_layer(self):
        """Stated from the other side: everything else is checked above."""
        tree = ast.parse(self.root().read_text(encoding="utf-8"), filename=str(self.root()))

        assert "sources" in _imports(tree), "app.py stopped composing the source layer"

    def test_the_root_exists_and_is_outside_the_general_scan(self):
        """Guards against the exemption silently covering nothing, or everything."""
        assert self.root().exists()
        assert self.root() not in modules()


class TestTheSourceLayerItself:
    """The exemption is for `sources/`, not for everything it touches."""

    def test_the_source_layer_does_not_import_a_renderer(self):
        """A source produces domain objects. It has no opinion about pixels."""
        for path in sorted((SRC / "sources").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

            forbidden = _imports(tree) & {"PIL", "render", "rendering", "view", "epdconfig"}
            assert forbidden == set(), f"{path.name} imports {sorted(forbidden)}"

    def test_the_source_layer_uses_no_third_party_http_client(self):
        """Standard library only: one dependency less, failure modes visible.

        Scanned as imports rather than as text, because `homeassistant.py`
        explains in its docstring *why* it does not use `homeassistant_api` -
        and naming the thing you refuse to depend on is not depending on it.
        """
        for path in sorted((SRC / "sources").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported = _imports(tree)

            forbidden = imported & {"homeassistant_api", "requests", "httpx", "aiohttp"}
            assert forbidden == set(), f"{path.name} imports {sorted(forbidden)}"


class TestTheScanItself:
    """A test that cannot fail is worse than no test."""

    def test_it_catches_a_leaked_attribute(self):
        tree = ast.parse("def render(snapshot):\n    return snapshot.entity_id\n")
        assert "entity_id" in identifiers(tree)

    def test_it_catches_a_leaked_string(self):
        tree = ast.parse('def render(state):\n    return state.get("hvac_action")\n')
        assert "hvac_action" in identifiers(tree)

    def test_it_catches_a_leaked_import(self):
        tree = ast.parse("from homeassistant_api import Client\n")
        assert "homeassistant_api" in identifiers(tree)

    def test_it_ignores_a_module_docstring(self):
        """`domain/models.py` says "no Home Assistant vocabulary" in prose."""
        tree = ast.parse('"""No Home Assistant vocabulary here."""\nx = 1\n')
        assert "No Home Assistant vocabulary here." not in identifiers(tree)

    def test_it_ignores_a_function_docstring(self):
        tree = ast.parse('def f():\n    """Never reads an entity_id."""\n    return 1\n')
        assert not any("entity_id" in name for name in identifiers(tree))

    def test_it_ignores_comments(self):
        """The AST drops them, which is the point of parsing rather than grepping."""
        tree = ast.parse("# entity_id is not our business\nx = 1\n")
        assert not any("entity_id" in name for name in identifiers(tree))

    def test_the_legacy_list_names_only_files_that_exist(self):
        """When M11 deletes a legacy module, this list must shrink with it."""
        stale = [name for name in LEGACY if not (SRC / name).exists()]
        assert stale == [], f"LEGACY names files that are gone: {stale}"

    def test_the_new_tree_is_actually_being_scanned(self):
        """The domain is the layer this rule exists to protect."""
        scanned = {path.relative_to(SRC).as_posix() for path in modules()}
        assert "domain/models.py" in scanned
        assert "domain/derive.py" in scanned
