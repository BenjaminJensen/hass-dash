"""The panel itself, driven as one indivisible unit of work.

This is the only module in the project that knows a Waveshare driver exists,
and it is deliberately the thinnest one that can be written: it turns a draw
list into the two planes `render/bmp.py` already builds, hands them to the
vendored `getbuffer()`, and performs the wake-write-sleep cycle the hardware
requires. Everything above it - the view, the policy, the loop - is the same
code that renders to a file.

**Sleep is part of a refresh, not a teardown.** HARDWARE.md section 3 quotes
the vendor: a panel left powered "will remain in a high voltage state for a
long time, which will damage the e-Paper and cannot be repaired." So `sleep()`
runs in a `finally`, and a display that raises halfway still puts the panel
down. The corollary is in the same paragraph - "after the screen enters sleep
mode, the sent image data will be ignored" - which is why `init()` runs at the
top of every cycle rather than once at start-up. Wake, init, display, sleep:
one unit, every time, no exceptions.

**The planes are built before the panel is woken.** Executing a draw list costs
about 12 ms and waking the panel costs 26 seconds of high-voltage refresh, so
the cheap work happens first and the panel is awake only for the write. If the
draw list is malformed, the panel is never woken at all.

**Constructing the panel is what claims the hardware, and that waits for the
first frame.** The pins and the SPI device belong to `render/panel/transport.py`,
which imports `gpiozero` and `spidev` inside its constructor - so every module
here is importable in the tools container, `--target epd` builds anywhere, and
only driving it needs a Pi. `open_panel()` is the one place that constructs a
transport, and `tests/test_hardware_boundary.py` asserts that from three sides.

Until M10 this was a lazy `importlib` call instead, because the vendored
`epd7in5b_V2` runs `epdconfig = RaspberryPi()` at module scope and importing it
*took* the four GPIO pins there and then. Nothing in `src/` imports it now.

**The double inversion is the driver's, and stays there.** `buffer()` inverts
every byte because PIL writes 0 for black and the panel reads 0 as white;
`display()` then inverts the black buffer back before sending it to `0x10`, and
sends the red buffer to `0x13` untouched (HARDWARE.md section 4). Both planes
go through `buffer()` and nothing here reimplements any of it.

**There is no partial path yet, and this class says so rather than faking one.**
`display_Partial()` writes one plane and cannot reach red at all; PLAN.md M9
decides whether it is worth building. Until then `partial_capable` is False,
the composition root pairs this target with a full-only cadence, and a partial
handed to `show()` is refused. Quietly promoting it to a full refresh would
flash the hallway every five minutes and spend the vendor's partial budget on
something that never happened.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from refresh.policy import Refresh
from render.bmp import BMPRenderer
from render.panel.driver import Panel
from render.panel.errors import PanelError
from render.panel.transport import SpiTransport
from view.drawlist import DrawItem

logger = logging.getLogger("dash.panel")

#: The command protocol the frame goes out over, for the log line. A V3 panel
#: driven by the V2 sequence is correct and documented in HARDWARE.md
#: section 2: there is no V3 variant, and the vendor states the two are
#: compatible. The name lost its `epd` prefix at M10, when the code behind it
#: stopped being the vendored `epd7in5b_V2` module.
DRIVER = "7in5b_V2"

__all__ = ["DRIVER", "EPDRenderer", "PanelError", "open_panel"]


def open_panel() -> Any:
    """Construct the panel, and claim the hardware doing it.

    The one line in the project that touches GPIO and SPI, kept a function so
    that a test can hand `EPDRenderer` a stand-in without a pin ever being
    taken. Importing this module is safe anywhere; calling this is not.
    """
    return Panel(SpiTransport())


class EPDRenderer:
    """A render target that puts the frame on the panel.

    The same `show(items, refresh)` the BMP target implements, so the loop in
    `app.py` cannot tell the two apart - which is what made M7's simulated day
    worth running against a file.
    """

    #: Short identifier for logs, naming the driver rather than the class, so a
    #: line says which panel the frame went to.
    name = f"epd:{DRIVER}"

    #: Whether a partial refresh can reach this target. See the module
    #: docstring; PLAN.md M9 is where this may change.
    partial_capable = False

    def __init__(
        self,
        renderer: BMPRenderer | None = None,
        opener: Callable[[], Any] | None = None,
    ) -> None:
        self.renderer = renderer or BMPRenderer()
        self.opener = opener or open_panel
        self._panel: Any = None

    def panel(self) -> Any:
        """The panel object, constructed once and kept.

        Once, because constructing the transport claims the GPIO pins for the
        life of the process and a second claim on them would fail. Kept,
        because a partial path would carry state across cycles - whether the
        window has been pre-filled - and M9 would put it on this instance.
        """
        if self._panel is None:
            self._panel = self.opener()
        return self._panel

    def show(self, items: tuple[DrawItem, ...], refresh: Refresh) -> None:
        """Put this frame on the glass, as one wake-write-sleep cycle."""
        if refresh is not Refresh.FULL:
            raise PanelError(
                f"this panel has no {refresh.value} path: the driver cannot write red "
                "outside a full refresh (HARDWARE.md section 4). PLAN.md M9 decides "
                "whether to build one."
            )

        planes = self.renderer.planes(items)
        panel = self.panel()

        expected = (panel.width, panel.height)
        if planes.black.size != expected or planes.red.size != expected:
            # The driver refuses this too, and says the same thing. It is
            # checked here as well because this is the layer that knows the
            # frame came from a draw list, and because a panel that is never
            # woken costs nothing.
            raise PanelError(f"the frame is {planes.black.size} and the panel is {expected}")

        black = panel.buffer(planes.black)
        red = panel.buffer(planes.red)

        try:
            panel.init()
            panel.display(black, red)
        finally:
            self._sleep(panel)

    def clear(self) -> None:
        """Blank the panel, as one wake-write-sleep cycle.

        Not part of any refresh: nothing in the loop calls this. It exists for
        the bench (PLAN.md M10.6) and for HARDWARE.md section 3's instruction
        to clear the screen before a panel is stored. The cycle is the same one
        `show()` performs, `finally` included, because the damage case does not
        care why the panel was woken.
        """
        panel = self.panel()
        try:
            panel.init()
            panel.clear()
        finally:
            self._sleep(panel)

    @staticmethod
    def _sleep(panel: Any) -> None:
        """Put the panel down, and never let that failure mask another one.

        A `sleep()` that raises inside the `finally` of a failed display would
        replace the real cause with a secondary one - and after a failed
        `init()` it will raise, because the SPI device was never opened. It is
        logged with its traceback instead, which is the only useful thing to do
        with it: there is nothing to retry, and the next cycle re-initialises
        from scratch anyway.

        A `sleep()` that hits the BUSY deadline lands here too. That is the
        right place for it: the panel has been told to power off and the frame
        has already been written or already failed, so there is nothing left
        for this cycle to do but say so.
        """
        try:
            panel.sleep()
        except Exception:
            logger.exception("panel=%s asleep=no", DRIVER)
