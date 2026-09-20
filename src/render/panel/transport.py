"""GPIO and SPI behind a small typed surface.

PLAN.md M10.2. The vendored `epdconfig.py` imports `gpiozero` and `spidev` at
module scope and `epd7in5b_V2.py` constructs a `RaspberryPi()` at module
scope, so importing the driver is not a declaration that hardware exists - it
is a *claim* on it, taken the moment the name is resolved. That is why
`render/epd.py` has always reached the driver through `importlib` and why
`tests/test_hardware_boundary.py` checks the rule from three sides.

**This module makes the distinction the vendored one collapses.** The imports
live inside `SpiTransport.__init__`, so the module is importable in the tools
container - where neither library exists - and only constructing the transport
touches a pin. `render.epd.open_panel()` is still the one place that does.

**Three lifecycle calls, not two.** The vendored `module_init()` /
`module_exit()` pair runs once per refresh: power up and open SPI, then close
SPI and drop the pins low again. It never closes the `gpiozero` devices, so
the process keeps its claim on the pins between cycles - which is correct, and
is also why nothing in the vendored code can ever give them back. So:

- `open()` is `module_init()`: power on, SPI open. Once per refresh.
- `power_down()` is `module_exit(cleanup=False)`: SPI closed, pins low. Once
  per refresh, at the end of `sleep()`.
- `close()` is the one the vendored code has no equivalent for: it releases
  the `gpiozero` devices, so a process that is done with the panel can hand
  the pins back instead of holding them until it exits.

**CS is absent on purpose.** The HAT wires chip select to CE0 (BCM 8) and
`spidev` drives it as part of every transfer. The vendored `send_command()`
toggles it by hand around every byte - and the vendored `digital_write()` has
that branch commented out, so those toggles have never reached a pin. Leaving
it out here changes nothing on the wire, which
`tests/test_panel_transcript.py` states as a fact rather than a hope.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Protocol

#: SPI as the vendored `module_init()` opens it: bus 0, device 0, 4 MHz,
#: mode 0 (CPOL=0, CPHA=0) per HARDWARE.md section 1.
SPI_BUS = 0
SPI_DEVICE = 0
SPI_HZ = 4_000_000
SPI_MODE = 0b00


class Pin(Enum):
    """The three pins the driver writes, named as HARDWARE.md section 5 names
    them so a transcript line reads the same as the wiring table."""

    RESET = "RST"
    DATA = "DC"
    POWER = "PWR"


#: BCM numbering, from HARDWARE.md section 5. CS (BCM 8) is driven by `spidev`
#: as CE0 and MOSI/SCLK (10/11) are the SPI bus itself, so none of the three
#: appears here.
BCM = {Pin.RESET: 17, Pin.DATA: 25, Pin.POWER: 18}
BUSY_BCM = 24


class Transport(Protocol):
    """Everything the driver needs from the world, and nothing else.

    Small enough that a recorder can implement it in a dozen lines, which is
    what puts the whole driver under test in a container with no hardware.
    """

    def open(self) -> None:
        """Power the module and open the SPI device."""

    def power_down(self) -> None:
        """Close SPI and drop the pins low, keeping the claim on them."""

    def close(self) -> None:
        """Release the pins."""

    def set_pin(self, pin: Pin, value: int) -> None:
        """Drive one output pin high (non-zero) or low."""

    def busy_pin(self) -> int:
        """Read BUSY. 0 means the panel is still working."""

    def write(self, data: bytes) -> None:
        """One short transfer - a command or a single argument byte."""

    def write_bulk(self, data: bytes) -> None:
        """One long transfer - a whole plane, in one call."""

    def delay_ms(self, milliseconds: float) -> None:
        """Wait, in the units the panel's datasheet uses."""


class SpiTransport:
    """The real one: `gpiozero` for the pins, `spidev` for the bus."""

    def __init__(
        self,
        speed_hz: int = SPI_HZ,
        bus: int = SPI_BUS,
        device: int = SPI_DEVICE,
    ) -> None:
        # Inside the constructor, not at module scope. This is the whole point
        # of the file: the import is the claim, so it happens where the claim
        # is wanted. AGENTS.md - neither library exists in the container.
        import gpiozero
        import spidev

        self.speed_hz = speed_hz
        self.bus = bus
        self.device = device

        self._spi = spidev.SpiDev()
        self._pins = {pin: gpiozero.LED(number) for pin, number in BCM.items()}
        self._busy = gpiozero.Button(BUSY_BCM, pull_up=False)
        self._opened = False

    def open(self) -> None:
        self._pins[Pin.POWER].on()
        self._spi.open(self.bus, self.device)
        self._spi.max_speed_hz = self.speed_hz
        self._spi.mode = SPI_MODE
        self._opened = True

    def power_down(self) -> None:
        self._spi.close()
        self._opened = False
        for pin in (Pin.RESET, Pin.DATA, Pin.POWER):
            self._pins[pin].off()

    def close(self) -> None:
        """Give the pins back.

        Idempotent, and it powers the module down first if that has not
        happened - a panel left powered is the damage case of HARDWARE.md
        section 3, and a `close()` that skipped it would be the one place in
        this project that walks away from a live panel.
        """
        if self._opened:
            self.power_down()
        for device in (*self._pins.values(), self._busy):
            device.close()

    def set_pin(self, pin: Pin, value: int) -> None:
        if value:
            self._pins[pin].on()
        else:
            self._pins[pin].off()

    def busy_pin(self) -> int:
        return int(self._busy.value)

    def write(self, data: bytes) -> None:
        self._spi.writebytes(list(data))

    def write_bulk(self, data: bytes) -> None:
        # `writebytes2` chunks a buffer larger than the kernel's SPI limit;
        # `writebytes` would refuse 48 000 bytes outright.
        self._spi.writebytes2(data)

    def delay_ms(self, milliseconds: float) -> None:
        time.sleep(milliseconds / 1000.0)
