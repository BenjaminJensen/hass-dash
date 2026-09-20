"""The bench tool, driven against a stand-in for the bench.

PLAN.md M10.6's script. What can be checked here is that it performs one
cycle, that it performs the one the flag asked for, and that it never opens a
panel to draw a frame it has not managed to build - the fixture load happens
first, so a broken config costs no electricity.

The measurement it exists to take cannot be taken here, which is the whole
point of it being a script rather than a test.
"""

from __future__ import annotations

import pytest

import panel_check
from refresh.policy import Refresh


class FakeTarget:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.items = None

    def show(self, items, refresh) -> None:
        self.calls.append(f"show:{refresh.value}")
        self.items = items

    def clear(self) -> None:
        self.calls.append("clear")


class TestWhatItDoes:
    def test_clear_blanks_the_panel_and_draws_nothing(self, capsys):
        target = FakeTarget()

        assert panel_check.main(["clear"], target=target) == 0
        assert target.calls == ["clear"]
        assert target.items is None

    def test_frame_draws_the_recorded_house_as_a_full_refresh(self, capsys):
        """A full refresh, because it is the only class this panel has
        (`render/epd.py`), and PLAN.md M9 has not changed that."""
        target = FakeTarget()

        assert panel_check.main(["frame"], target=target) == 0
        assert target.calls == [f"show:{Refresh.FULL.value}"]
        assert len(target.items) > 50

    def test_it_reports_both_clocks(self, capsys):
        """The wall clock is the panel's 26 seconds; the CPU clock is the
        number M10 exists to move - 29.9 s under the vendored busy loop."""
        panel_check.main(["clear"], target=FakeTarget())
        printed = capsys.readouterr().out

        assert "wall=" in printed and "cpu=" in printed
        assert "29.9" in printed
        assert "180" in printed, "the vendor floor is the one thing a bench run forgets"

    def test_an_unknown_operation_is_rejected_by_the_parser(self):
        with pytest.raises(SystemExit):
            panel_check.main(["init"], target=FakeTarget())


class TestItDoesNotTouchHardwareToFindOutSomethingIsWrong:
    def test_a_bad_house_file_fails_before_a_panel_is_built(self, tmp_path, monkeypatch):
        """The frame is built before the target, not after - the same order
        `EPDRenderer.show()` uses, and for the same reason: a configuration
        error must not cost anything at the panel."""
        built = []
        monkeypatch.setattr(panel_check, "EPDRenderer", lambda: built.append(1))
        broken = tmp_path / "house.yml"
        broken.write_text("rooms: []\n", encoding="utf-8")

        with pytest.raises(Exception):
            panel_check.main(["frame", "--house", str(broken)])

        assert built == []

    def test_the_default_target_is_the_panel(self):
        """No `--target` flag: this script has exactly one purpose and a flag
        that let it write a BMP would make it a worse `render_fixture.py`."""
        import inspect

        source = inspect.getsource(panel_check.main)

        assert "EPDRenderer()" in source
