"""The panel target, proved against a stand-in for the panel.

AGENTS.md is explicit that GPIO and SPI do not exist in this container, so what
can be tested here is everything except the electricity: that the cycle is
wake, init, display, sleep in that order and every time; that the panel is put
back to sleep even when the write fails, because HARDWARE.md section 3 says a
panel left powered is permanently damaged; that both planes go through the
driver's own `getbuffer()` so the double inversion is never reimplemented; and
that a refresh class the driver has no path for is refused rather than quietly
turned into one it does.

The stand-in records calls and can be made to fail at each step. What it does
*not* do is check its own arguments: `tests/test_panel_driver.py` holds
`render/panel/driver.py` to the vendored driver's transcript, and this file is
about the cycle around it.
"""

from __future__ import annotations

import inspect

import pytest

from refresh.policy import Refresh
from render.epd import DRIVER, EPDRenderer, PanelError, open_panel
from view.drawlist import Box, Colour, DrawItem, Primitive, UpdateClass

BOX = Box(0, 0, 64, 32)


def frame(colour: Colour = Colour.BLACK) -> tuple[DrawItem, ...]:
    return (
        DrawItem(
            primitive=Primitive.FILL,
            box=BOX,
            colour=colour,
            update=UpdateClass.FULL,
            region="test",
        ),
    )


class FakePanel:
    """What `render.panel.driver.Panel` looks like from this side."""

    def __init__(self, width: int = 800, height: int = 480):
        self.width = width
        self.height = height
        self.calls: list[str] = []
        self.shown: list[tuple] = []
        self.init_raises: Exception | None = None
        self.display_raises: Exception | None = None
        self.sleep_raises: Exception | None = None

    def buffer(self, image):
        self.calls.append("buffer")
        return b"\x00" * (self.width // 8 * self.height)

    def init(self) -> None:
        self.calls.append("init")
        if self.init_raises is not None:
            raise self.init_raises

    def display(self, black, red) -> None:
        self.calls.append("display")
        self.shown.append((black, red))
        if self.display_raises is not None:
            raise self.display_raises

    def clear(self) -> None:
        self.calls.append("clear")

    def sleep(self) -> None:
        self.calls.append("sleep")
        if self.sleep_raises is not None:
            raise self.sleep_raises


@pytest.fixture
def panel():
    return FakePanel()


@pytest.fixture
def renderer(panel):
    return EPDRenderer(opener=lambda: panel)


class TestTheCycle:
    def test_it_is_init_then_display_then_sleep(self, renderer, panel):
        """HARDWARE.md section 3: waking, writing and sleeping is the unit."""
        renderer.show(frame(), Refresh.FULL)

        assert [call for call in panel.calls if call != "buffer"] == [
            "init",
            "display",
            "sleep",
        ]

    def test_every_cycle_initialises_again(self, renderer, panel):
        """ "After the screen enters sleep mode, the sent image data will be
        ignored" - so an `init()` per refresh, not one at start-up."""
        renderer.show(frame(), Refresh.FULL)
        renderer.show(frame(), Refresh.FULL)

        assert [call for call in panel.calls if call != "buffer"] == [
            "init",
            "display",
            "sleep",
            "init",
            "display",
            "sleep",
        ]

    def test_both_planes_go_through_the_drivers_own_buffer(self, renderer, panel):
        """The double inversion is the driver's, and is never reimplemented."""
        renderer.show(frame(), Refresh.FULL)

        assert panel.calls.count("buffer") == 2
        black, red = panel.shown[0]
        assert len(black) == len(red) == 800 // 8 * 480

    def test_the_planes_are_built_before_the_panel_is_woken(self, panel):
        """A malformed draw list must not cost 26 seconds of high voltage."""

        class Exploding:
            def planes(self, items):
                raise ValueError("nope")

        with pytest.raises(ValueError):
            EPDRenderer(renderer=Exploding(), opener=lambda: panel).show(frame(), Refresh.FULL)

        assert panel.calls == []


class TestClearing:
    """Not part of any refresh, and the same cycle regardless.

    `HARDWARE.md` section 3 says to clear the screen before storing a panel,
    and PLAN.md M10.6 wants one `Clear()` watched on the glass. Neither is a
    reason to leave a panel powered, so this takes the same route `show()`
    does.
    """

    def test_it_is_init_then_clear_then_sleep(self, renderer, panel):
        renderer.clear()

        assert panel.calls == ["init", "clear", "sleep"]

    def test_a_failed_clear_still_puts_the_panel_down(self, renderer, panel):
        panel.init_raises = PanelError("no")

        with pytest.raises(PanelError):
            renderer.clear()

        assert panel.calls[-1] == "sleep"

    def test_it_draws_nothing_and_so_needs_no_planes(self, renderer, panel):
        """The panel blanks itself from its own constants; there is no frame
        to build and no draw list to be wrong."""
        renderer.clear()

        assert "buffer" not in panel.calls


class TestSleepIsNotOptional:
    def test_a_failed_write_still_puts_the_panel_down(self, renderer, panel):
        """The damage case: a panel left in a high voltage state (section 3)."""
        panel.display_raises = RuntimeError("SPI went away")

        with pytest.raises(RuntimeError):
            renderer.show(frame(), Refresh.FULL)

        assert panel.calls[-1] == "sleep"

    def test_a_panel_that_will_not_initialise_is_still_put_down(self, renderer, panel):
        panel.init_raises = PanelError("the panel would not initialise")

        with pytest.raises(PanelError) as error:
            renderer.show(frame(), Refresh.FULL)

        assert "initialise" in str(error.value)
        assert panel.calls[-1] == "sleep"
        assert "display" not in panel.calls

    def test_a_sleep_that_fails_does_not_mask_the_real_failure(self, renderer, panel):
        """After a failed `init()` the SPI device was never opened, so `sleep()`
        raises too. The first exception is the one worth keeping."""
        panel.init_raises = PanelError("the panel would not initialise")
        panel.sleep_raises = RuntimeError("no such device")

        with pytest.raises(PanelError):
            renderer.show(frame(), Refresh.FULL)

    def test_a_sleep_that_fails_on_a_good_cycle_is_logged_not_swallowed(
        self, renderer, panel, caplog
    ):
        panel.sleep_raises = RuntimeError("no such device")

        renderer.show(frame(), Refresh.FULL)

        assert "asleep=no" in caplog.text


class TestWhatItRefuses:
    @pytest.mark.parametrize("refresh", [Refresh.PARTIAL, Refresh.NONE])
    def test_it_has_no_path_for_anything_but_a_full_refresh(self, renderer, panel, refresh):
        """Promoting a partial to a full would flash the hallway every five
        minutes and spend a budget on a refresh that never happened."""
        with pytest.raises(PanelError) as error:
            renderer.show(frame(), refresh)

        assert refresh.value in str(error.value)
        assert panel.calls == []

    def test_it_says_so_in_the_attribute_the_composition_root_reads(self, renderer):
        assert renderer.partial_capable is False

    def test_a_frame_the_wrong_size_is_refused_rather_than_blanked(self, panel):
        """The vendored `getbuffer()` answered a bad size with a blank buffer
        and a warning, which reaches the wall as a cleared screen and no error
        anywhere. Refused here before the panel is woken, and refused again by
        `render/panel/driver.py` for anyone who calls it directly."""
        renderer = EPDRenderer(opener=lambda: panel)
        renderer.renderer.size = (400, 300)

        with pytest.raises(PanelError) as error:
            renderer.show(frame(), Refresh.FULL)

        assert "(400, 300)" in str(error.value)
        assert panel.calls == []


class TestThePanelObject:
    def test_it_is_opened_once_and_kept(self, panel):
        """Constructing the transport holds the GPIO pins for the life of the
        process; a second claim on them would fail."""
        opens = []

        def opener():
            opens.append(1)
            return panel

        renderer = EPDRenderer(opener=opener)
        renderer.show(frame(), Refresh.FULL)
        renderer.show(frame(), Refresh.FULL)

        assert len(opens) == 1

    def test_it_is_not_opened_by_construction(self):
        """So that `--target epd` can be built anywhere and only fails when it
        is driven - which is the honest place for a missing panel to show up."""
        opens = []
        EPDRenderer(opener=lambda: opens.append(1))

        assert opens == []

    def test_the_name_says_which_driver_drove_the_frame(self, renderer):
        """It changed at M10, and the log line changed with it: the frame no
        longer goes out through the vendored `epd7in5b_V2` module, and a
        journal that still said so would be wrong about the one thing this
        field is for."""
        assert renderer.name == f"epd:{DRIVER}"
        assert DRIVER == "7in5b_V2"

    def test_it_builds_the_panel_this_project_owns(self):
        """`open_panel()` is the whole blast radius of M10's rewrite, which is
        what the function was for."""
        source = inspect.getsource(open_panel)

        assert "Panel(SpiTransport())" in source

    def test_opening_for_real_needs_hardware_this_container_has_not_got(self):
        """The one line in the project that claims the pins, shown failing for
        the reason it should fail for here: `SpiTransport` imports `gpiozero`
        and `spidev`, and AGENTS.md says neither exists in this container."""
        with pytest.raises(ImportError):
            open_panel()
