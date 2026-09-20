"""The electricity, and the seam that keeps it out of this container.

PLAN.md M10.2. Almost nothing here can be exercised: `SpiTransport` is the one
class in the project whose whole job is to touch hardware, and AGENTS.md says
the hardware is not here. So what this file checks is the seam rather than the
behaviour - that the module imports cleanly, that constructing it is the thing
that claims the pins, that the numbers match HARDWARE.md section 5, and that
the recorder every other panel test runs against implements the same surface
as the real one.

That last one is the trap this file exists to close. A stand-in that is a
little smaller than the real thing lets a driver pass its whole test suite
against a method the hardware does not have.
"""

from __future__ import annotations

import inspect
import sys

import pytest

from render.panel.transport import (
    BCM,
    BUSY_BCM,
    SPI_BUS,
    SPI_DEVICE,
    SPI_HZ,
    SPI_MODE,
    Pin,
    SpiTransport,
    Transport,
)
from tests.panel_harness import RecordingTransport

#: The surface, taken from the Protocol rather than repeated, so a method
#: added there is a method both implementations are immediately held to.
SURFACE = tuple(name for name in vars(Transport) if not name.startswith("_"))


class TestTheSeam:
    def test_the_module_imports_without_hardware(self):
        """It is imported at the top of this file. Reaching this line is the
        assertion; the rest states what that means."""
        assert "gpiozero" not in sys.modules
        assert "spidev" not in sys.modules

    def test_constructing_it_is_what_claims_the_pins(self):
        """The vendored `epdconfig` imports both libraries at module scope and
        `epd7in5b_V2` constructs a `RaspberryPi()` at module scope, so the
        import *is* the claim. Here the claim waits for the constructor, which
        is why `--target epd` can be built in this container and only driving
        it fails."""
        with pytest.raises(ImportError):
            SpiTransport()

    def test_the_import_is_inside_the_constructor_and_not_deeper(self):
        """A lazy import inside each method would work too and would be worse:
        the claim would be spread over eight call sites instead of one."""
        source = inspect.getsource(SpiTransport.__init__)

        assert "import gpiozero" in source
        assert "import spidev" in source


class TestTheNumbersMatchTheWiring:
    def test_the_pins_are_the_ones_in_hardware_md_section_5(self):
        assert BCM == {Pin.RESET: 17, Pin.DATA: 25, Pin.POWER: 18}
        assert BUSY_BCM == 24

    def test_chip_select_and_the_bus_pins_are_not_driven_by_hand(self):
        """CS is CE0 and `spidev` drives it; MOSI and SCLK are the bus. The
        vendored config's CS branch is commented out, so leaving all three out
        changes nothing on the wire - `tests/test_panel_driver.py` asserts
        that against the transcript."""
        assert set(BCM) == {Pin.RESET, Pin.DATA, Pin.POWER}

    def test_spi_is_opened_the_way_the_vendored_module_init_opens_it(self):
        """4 MHz, mode 0 (CPOL=0, CPHA=0) per HARDWARE.md section 1. A frame is
        48 000 bytes, so the bus speed is the one number here that a person
        would notice if it were wrong."""
        assert (SPI_BUS, SPI_DEVICE, SPI_HZ, SPI_MODE) == (0, 0, 4_000_000, 0b00)


class TestTheStandInIsNotSmallerThanTheRealThing:
    def test_the_surface_is_worth_checking(self):
        assert len(SURFACE) >= 8

    @pytest.mark.parametrize("name", SURFACE)
    def test_both_implementations_have_it(self, name):
        assert callable(getattr(SpiTransport, name, None)), f"SpiTransport lacks {name}"
        assert callable(getattr(RecordingTransport, name, None)), f"the recorder lacks {name}"

    @pytest.mark.parametrize("name", SURFACE)
    def test_they_take_the_same_arguments(self, name):
        """By parameter name, not by annotation: the recorder takes a
        `Transcript`'s idea of a pin and the real one takes a `gpiozero`
        device, and that difference is the point of the seam."""
        expected = list(inspect.signature(getattr(Transport, name)).parameters)

        for implementation in (SpiTransport, RecordingTransport):
            actual = list(inspect.signature(getattr(implementation, name)).parameters)
            assert actual == expected, f"{implementation.__name__}.{name}{tuple(actual)}"
