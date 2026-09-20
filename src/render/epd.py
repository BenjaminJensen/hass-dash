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

**The driver is imported lazily, and importing it is a side effect.**
`epd7in5b_V2` does `epdconfig = RaspberryPi()` at module scope, and that
constructor claims five GPIO pins through `gpiozero` and opens `spidev`. So the
import is not a declaration that the hardware exists - it is a claim on it.
Nothing in this file happens at module scope for that reason, and
`tests/test_hardware_boundary.py` asserts that no module the suite can reach
pulls `epdconfig` in before a test has decided to. The tools container has
neither library, per AGENTS.md.

**The double inversion is the driver's, and stays there.** `getbuffer()`
inverts every byte because PIL writes 0 for black and the panel reads 0 as
white; `display()` then inverts the black buffer back before sending it to
`0x10`, and sends the red buffer to `0x13` untouched (HARDWARE.md section 4).
Both planes go through `getbuffer()` and nothing here reimplements any of it.

**There is no partial path yet, and this class says so rather than faking one.**
`display_Partial()` writes one plane and cannot reach red at all; PLAN.md M9
decides whether it is worth building. Until then `partial_capable` is False,
the composition root pairs this target with a full-only cadence, and a partial
handed to `show()` is refused. Quietly promoting it to a full refresh would
flash the hallway every five minutes and spend the vendor's partial budget on
something that never happened.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

from refresh.policy import Refresh
from render.bmp import BMPRenderer
from view.drawlist import DrawItem

logger = logging.getLogger("dash.panel")

#: The vendored driver, by name. A V3 panel on a V2 driver is correct and
#: documented in HARDWARE.md section 2: there is no V3 variant, and the vendor
#: states the two are compatible.
DRIVER = "epd7in5b_V2"


class PanelError(RuntimeError):
    """The frame did not reach the glass.

    Raised for a panel that would not initialise, a plane the panel cannot
    accept, and a refresh class this renderer has no path for. The loop catches
    it like any other target failure: the cycle is not recorded, so the floor,
    the keep-alive and the partial budget all behave as though it never
    happened, and the next tick tries again.
    """


def open_panel() -> Any:
    """Import the vendored driver and construct the panel.

    Split out as a function so that a test can hand `EPDRenderer` a stand-in
    without the import ever being attempted, and so that the one line in the
    project that touches hardware is one line.
    """
    return importlib.import_module(DRIVER).EPD()


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

        Once, because the driver's module-scope `RaspberryPi()` holds the GPIO
        pins for the life of the process and a second claim on them would fail.
        Kept, because `partFlag` - the driver's "have I done a partial yet"
        state - lives on the instance and M9 will depend on it.
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
            # `getbuffer()` answers a size it does not recognise with a warning
            # and a blank buffer, which reaches the wall as a cleared screen
            # and no error anywhere. Refuse instead.
            raise PanelError(f"the frame is {planes.black.size} and the panel is {expected}")

        black = panel.getbuffer(planes.black)
        red = panel.getbuffer(planes.red)

        try:
            if panel.init() != 0:
                raise PanelError("the panel would not initialise")
            panel.display(black, red)
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
        """
        try:
            panel.sleep()
        except Exception:
            logger.exception("panel=%s asleep=no", DRIVER)
