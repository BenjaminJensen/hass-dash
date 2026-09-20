"""The Waveshare 7.5" (B) full-refresh path, rewritten and tested.

PLAN.md M10.3. Same commands, same order, same bytes as the vendored
`epd7in5b_V2.py` - asserted line by line against the transcripts recorded from
it in `tests/fixtures/transcripts/`. What is different is different on
purpose, and each difference is a named assertion in
`tests/test_panel_driver.py` rather than something to be discovered on a wall:

**The BUSY wait has a deadline and sleeps between polls.** The vendored loop
has neither. With no timeout, a panel that never releases BUSY holds the
process there forever - the unit is still "running", the journal says nothing,
and the wall keeps yesterday's frame until somebody notices. That is the worst
failure available here and it is the reason this file exists. With no delay,
the loop re-sends `0x71` as fast as CPython will go for the full 26 seconds:
29.9 s of CPU in a 32 s cycle, measured on the board (HARDWARE.md section 4).

The two numbers are chosen rather than inherited. **10 ms** between polls: the
vendor's own `delay_ms(200)` after the loop is the scale, so 10 ms adds at most
10 ms to a 26 000 ms refresh and takes the spin from ~430 000 polls to ~2 600.
**40 s** for the deadline: comfortably past a 26 s refresh, and comfortably
inside the unit's `TimeoutStopSec=45s`, so a hung panel raises before systemd
starts killing things. `PanelError` is exactly the right shape for it - the
loop does not record the cycle, so the floor, the keep-alive and the budget
behave as though it never happened, and the next tick tries again.

**Nothing mutates the caller's buffer.** The vendored `display()` inverts
`imageblack` in place, so the same buffer sent twice draws its own negative the
second time. Nothing does that today because `show()` rebuilds both planes
every cycle - but a retry written later would, and it would look like a driver
fault rather than a caller one. `buffer()` returns immutable `bytes` and the
inversion is a `bytes.translate()`, which is also 90x faster than the Python
`for` loop it replaces: 0.326 ms against 29.3 ms per plane on this board,
three planes per frame.

**A frame the wrong size raises.** The vendored `getbuffer()` answers a size it
does not recognise with a warning and a blank buffer, which reaches the wall as
a cleared screen with nothing in the log to explain it - and a blank dashboard
looks like a quiet house rather than a broken program.

**There is no partial path here, and no flat-fill path.** `init_part()`,
`display_Partial()` and `display_Base_color()` are not ported. PLAN.md M9
decides whether a partial path is built at all, and the vendored window
arithmetic it would be built on is provably wrong (HARDWARE.md section 4).
`display_Base_color()` sends `~color`, which is `-1` for `0x00`, and sends it
one byte per SPI transaction - 48 000 transactions where one would do.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from render.panel.errors import PanelError
from render.panel.transport import Pin, Transport

logger = logging.getLogger("dash.panel")

#: HARDWARE.md section 1. The panel is 800x480 and the driver does not ask.
WIDTH = 800
HEIGHT = 480

#: One-bit planes, packed eight pixels to the byte.
PLANE_BYTES = WIDTH // 8 * HEIGHT

#: How long to wait between BUSY polls, and how long to wait at all. See the
#: module docstring for why these two numbers and not others.
POLL_MS = 10
BUSY_TIMEOUT_S = 40.0

#: 0 <-> 255. PIL writes 0 for black and the panel reads 0 as white, so a
#: plane is inverted on the way into a buffer and the black one is inverted
#: back on the way out (HARDWARE.md, "Buffer convention").
INVERT = bytes(255 - value for value in range(256))

# The UC8179 commands this path uses, by their datasheet names. The vendored
# driver spells them as bare hex; the bytes on the wire are identical.
POWER_SETTING = 0x01
POWER_OFF = 0x02
POWER_ON = 0x04
BOOSTER_SOFT_START = 0x06
DEEP_SLEEP = 0x07
PANEL_SETTING = 0x00
TRANSMISSION_BLACK = 0x10
DISPLAY_REFRESH = 0x12
TRANSMISSION_RED = 0x13
DUAL_SPI = 0x15
VCOM_AND_DATA_INTERVAL = 0x50
TCON_SETTING = 0x60
RESOLUTION_SETTING = 0x61
GET_STATUS = 0x71


class Panel:
    """The panel's command protocol, over any transport.

    Constructing one claims nothing: the transport decides whether it owns
    hardware or a recorder, which is what lets every command sequence in this
    file be asserted in a container that has no SPI bus.
    """

    width = WIDTH
    height = HEIGHT

    def __init__(
        self,
        transport: Transport,
        monotonic: Callable[[], float] = time.monotonic,
        timeout_s: float = BUSY_TIMEOUT_S,
        poll_ms: float = POLL_MS,
    ) -> None:
        self.transport = transport
        self.monotonic = monotonic
        self.timeout_s = timeout_s
        self.poll_ms = poll_ms

    # -- the frame --------------------------------------------------------

    def buffer(self, image: Any) -> bytes:
        """One PIL `"1"` plane as the bytes the panel takes, inverted."""
        if image.size != (self.width, self.height):
            raise PanelError(
                f"the frame is {image.size} and the panel is {(self.width, self.height)}"
            )
        return image.convert("1").tobytes("raw").translate(INVERT)

    # -- the cycle --------------------------------------------------------

    def init(self) -> None:
        """Wake the panel and configure it for a full refresh.

        Every cycle, not once at start-up: "after the screen enters sleep
        mode, the sent image data will be ignored" (HARDWARE.md section 3).
        """
        self.transport.open()
        self._reset()

        self._command(POWER_SETTING)
        self._data(0x07, 0x07, 0x3F, 0x3F)

        self._command(BOOSTER_SOFT_START)
        self._data(0x17, 0x17, 0x28, 0x17)

        self._command(POWER_ON)
        self.transport.delay_ms(100)
        self._wait_ready()

        self._command(PANEL_SETTING)
        self._data(0x0F)

        self._command(RESOLUTION_SETTING)
        self._data(0x03, 0x20, 0x01, 0xE0)  # 800 x 480

        self._command(DUAL_SPI)
        self._data(0x00)

        self._command(VCOM_AND_DATA_INTERVAL)
        self._data(0x11, 0x07)

        self._command(TCON_SETTING)
        self._data(0x22)

    def display(self, black: bytes, red: bytes) -> None:
        """Write both planes and refresh. This is the 26 seconds."""
        self._check_plane(black, "black")
        self._check_plane(red, "red")

        self._command(TRANSMISSION_BLACK)
        # Inverted back, so what reaches 0x10 is the plane PIL produced. The
        # caller's buffer is untouched - `translate` returns a new object.
        self._bulk(black.translate(INVERT))

        self._command(TRANSMISSION_RED)
        self._bulk(red)

        self._refresh()

    def clear(self) -> None:
        """Blank both planes, in two transfers rather than 96 000."""
        self._command(TRANSMISSION_BLACK)
        self._bulk(b"\xff" * PLANE_BYTES)

        self._command(TRANSMISSION_RED)
        self._bulk(b"\x00" * PLANE_BYTES)

        self._refresh()

    def sleep(self) -> None:
        """Put the panel down and power the module off.

        Not a teardown - part of every refresh. A panel left powered "will
        remain in a high voltage state for a long time, which will damage the
        e-Paper and cannot be repaired" (HARDWARE.md section 3).
        """
        self._command(POWER_OFF)
        self._wait_ready()

        self._command(DEEP_SLEEP)
        self._data(0xA5)

        self.transport.delay_ms(2000)
        self.transport.power_down()

    def close(self) -> None:
        """Hand the pins back. Nothing in a refresh cycle calls this."""
        self.transport.close()

    # -- the wire ---------------------------------------------------------

    def _reset(self) -> None:
        """The hardware reset pulse: high, low for 4 ms, high."""
        self.transport.set_pin(Pin.RESET, 1)
        self.transport.delay_ms(200)
        self.transport.set_pin(Pin.RESET, 0)
        self.transport.delay_ms(4)
        self.transport.set_pin(Pin.RESET, 1)
        self.transport.delay_ms(200)

    def _command(self, code: int) -> None:
        self.transport.set_pin(Pin.DATA, 0)
        self.transport.write(bytes([code]))

    def _data(self, *values: int) -> None:
        """Argument bytes, one transfer each, as the panel expects them."""
        for value in values:
            self.transport.set_pin(Pin.DATA, 1)
            self.transport.write(bytes([value]))

    def _bulk(self, data: bytes) -> None:
        self.transport.set_pin(Pin.DATA, 1)
        self.transport.write_bulk(data)

    def _refresh(self) -> None:
        self._command(DISPLAY_REFRESH)
        self.transport.delay_ms(100)
        self._wait_ready()

    def _wait_ready(self) -> None:
        """Poll BUSY until the panel answers, or give up and say so."""
        deadline = self.monotonic() + self.timeout_s

        while True:
            self._command(GET_STATUS)
            if self.transport.busy_pin() != 0:
                break
            if self.monotonic() >= deadline:
                raise PanelError(
                    f"the panel held BUSY for more than {self.timeout_s:g} s. "
                    "A refresh takes about 26 s (HARDWARE.md section 1), so it has "
                    "stopped answering; the frame did not reach the glass."
                )
            self.transport.delay_ms(self.poll_ms)

        self.transport.delay_ms(200)

    @staticmethod
    def _check_plane(data: bytes, which: str) -> None:
        """A plane of the wrong length would leave the panel mid-transfer."""
        if len(data) != PLANE_BYTES:
            raise PanelError(
                f"the {which} plane is {len(data)} bytes and the panel takes {PLANE_BYTES}"
            )
