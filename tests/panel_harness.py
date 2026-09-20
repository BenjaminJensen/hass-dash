"""A recorder in `sys.modules`, and the transcript it produces.

PLAN.md M10.1. The vendored `EPD` class imports neither `gpiozero` nor
`spidev`: it talks to exactly one object - the module-scope `epdconfig` - and
only through seven methods. Put a recorder there before importing
`epd7in5b_V2` and the whole driver runs in the tools container, emitting the
precise sequence of pin writes, SPI bytes and delays it would emit on the Pi.
**That transcript is the specification** the replacement in `render/panel/` is
proven against, and it costs no hardware.

**The transcript records effects, not calls.** `send_command()` toggles CS
around every byte, and `RaspberryPi.digital_write()` has its CS branch
commented out - spidev drives CE0 itself - so those toggles reach no pin at
all. The recorder mirrors that dispatch rather than the call, which is both
what the wire sees and what lets a driver that never mentions CS produce a
byte-identical transcript. The same goes for `digital_read()` on anything but
BUSY: the vendored code reads `self.RST_PIN.value`, where `RST_PIN` is the
integer 17, so those three branches are `AttributeError`s. The recorder raises
one too rather than inventing a reading nothing can take.

Bulk writes are recorded as a length and a SHA-256 rather than 48 000 bytes of
hex: a digest is exact, a transcript file stays readable, and a plane that
changed by one pixel still fails the comparison.

**Re-recording.** The committed transcripts under
`tests/fixtures/transcripts/` come from the vendored driver, which stays in the
tree as the reference (PLAN.md M10.5). To re-record after an upstream change::

    docker compose run --rm --entrypoint python tools tests/panel_harness.py

then diff. The difference *is* the upstream fix, which is what makes a fork
payable.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

#: Where the recorded specification lives.
TRANSCRIPTS = Path(__file__).parent / "fixtures" / "transcripts"

#: The vendored driver and its pin configuration, by module name. Imported
#: here and nowhere else in the project (PLAN.md M10.5).
VENDORED_DRIVER = "epd7in5b_V2"
VENDORED_CONFIG = "epdconfig"

#: SPI as `RaspberryPi.module_init()` opens it.
SPI_OPEN = "spi open bus=0 device=0 hz=4000000 mode=0"


class Transcript:
    """One line per effect that reaches the hardware.

    Both recorders write through this class, so a difference between the
    vendored driver and its replacement can only be a difference in what the
    panel would see.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []

    def pin(self, name: str, value: Any) -> None:
        self.lines.append(f"pin {name} {1 if value else 0}")

    def read(self, name: str, value: int) -> None:
        self.lines.append(f"read {name} {value}")

    def delay(self, milliseconds: float) -> None:
        self.lines.append(f"delay {milliseconds:g}")

    def write(self, data: bytes) -> None:
        self.lines.append(f"write {data.hex(' ')}")

    def write_bulk(self, data: bytes) -> None:
        digest = hashlib.sha256(data).hexdigest()
        self.lines.append(f"write2 {len(data)} sha256={digest}")

    def spi_open(self) -> None:
        self.lines.append(SPI_OPEN)

    def spi_close(self) -> None:
        self.lines.append("spi close")

    def release(self) -> None:
        self.lines.append("release")

    @property
    def text(self) -> str:
        return "".join(f"{line}\n" for line in self.lines)


class RecordingConfig:
    """What `epdconfig.RaspberryPi` looks like from the driver's side.

    The seven methods the driver calls, the pin constants it reads off the
    instance, and a scripted BUSY pin so that `ReadBusy()` terminates - which
    the real one, having no timeout, is not guaranteed to do.
    """

    # The pin numbers of HARDWARE.md section 5, as the vendored class states
    # them. The driver copies these onto itself in `EPD.__init__`.
    RST_PIN = 17
    DC_PIN = 25
    CS_PIN = 8
    BUSY_PIN = 24
    PWR_PIN = 18
    MOSI_PIN = 10
    SCLK_PIN = 11

    def __init__(self, transcript: Transcript, busy: Sequence[int] = (1,)) -> None:
        self.transcript = transcript
        #: BUSY pin readings in order; the last one repeats forever. 0 is busy.
        self.busy = list(busy) or [1]
        self.polls = 0

    # -- the seven methods ------------------------------------------------

    def digital_write(self, pin: int, value: int) -> None:
        if pin == self.RST_PIN:
            self.transcript.pin("RST", value)
        elif pin == self.DC_PIN:
            self.transcript.pin("DC", value)
        elif pin == self.PWR_PIN:
            self.transcript.pin("PWR", value)
        # CS falls through, exactly as it does in the vendored class, where the
        # branch is commented out. See the module docstring.

    def digital_read(self, pin: int) -> int:
        if pin != self.BUSY_PIN:
            # `self.RST_PIN.value` on an integer. Three dead branches, and the
            # recorder is the place that says so out loud.
            raise AttributeError("'int' object has no attribute 'value'")
        value = self.busy[min(self.polls, len(self.busy) - 1)]
        self.polls += 1
        self.transcript.read("BUSY", value)
        return value

    def delay_ms(self, delaytime: float) -> None:
        self.transcript.delay(delaytime)

    def spi_writebyte(self, data: Sequence[int]) -> None:
        self.transcript.write(bytes(data))

    def spi_writebyte2(self, data: Sequence[int] | bytes | bytearray) -> None:
        self.transcript.write_bulk(bytes(data))

    def module_init(self, cleanup: bool = False) -> int:
        self.transcript.pin("PWR", 1)
        self.transcript.spi_open()
        return 0

    def module_exit(self, cleanup: bool = False) -> None:
        self.transcript.spi_close()
        self.transcript.pin("RST", 0)
        self.transcript.pin("DC", 0)
        self.transcript.pin("PWR", 0)
        if cleanup:
            self.transcript.release()


@contextmanager
def vendored_panel(transcript: Transcript, busy: Sequence[int] = (1,)) -> Iterator[Any]:
    """The vendored `EPD`, wired to a recorder instead of to a Raspberry Pi.

    The driver does `epdconfig = RaspberryPi()` at module scope, so the fake
    has to be in `sys.modules` *before* the import and the driver has to be
    re-imported for every recording. Both names are restored afterwards, which
    is what keeps `tests/test_hardware_boundary.py` true: the import happens
    inside this fixture and nowhere else.
    """
    saved = {name: sys.modules.get(name) for name in (VENDORED_CONFIG, VENDORED_DRIVER)}

    fake = types.ModuleType(VENDORED_CONFIG)
    fake.RaspberryPi = lambda: RecordingConfig(transcript, busy)  # type: ignore[attr-defined]
    sys.modules[VENDORED_CONFIG] = fake
    sys.modules.pop(VENDORED_DRIVER, None)

    try:
        yield importlib.import_module(VENDORED_DRIVER).EPD()
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


# ---------------------------------------------------------------------------
# The frame the transcripts are recorded against
# ---------------------------------------------------------------------------


def plane(offset: int) -> Any:
    """A deterministic 800x480 one-bit plane.

    Synthetic rather than a rendered screen: a transcript that changed every
    time a font or a layout moved would be a test of the view layer wearing a
    driver's clothes. The two planes differ, so a driver that swapped them -
    or sent the same one twice - fails on the digests.
    """
    from PIL import Image, ImageDraw

    image = Image.new("1", (800, 480), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((offset, offset, offset + 320, offset + 200), fill=0)
    draw.rectangle((offset + 40, offset + 40, offset + 80, offset + 80), fill=255)
    draw.line((0, offset, 799, 479 - offset), fill=0, width=3)
    return image


BLACK_PLANE = plane(8)
RED_PLANE = plane(64)


def vendored_operations(epd: Any) -> dict[str, Any]:
    """The four full-refresh operations, as the vendored driver spells them."""
    return {
        "init": epd.init,
        "display": lambda: epd.display(epd.getbuffer(BLACK_PLANE), epd.getbuffer(RED_PLANE)),
        "clear": epd.Clear,
        "sleep": epd.sleep,
    }


def record_vendored(name: str, busy: Sequence[int] = (1,)) -> Transcript:
    """Run one operation against the recorder and return what it emitted."""
    transcript = Transcript()
    with vendored_panel(transcript, busy) as epd:
        vendored_operations(epd)[name]()
    return transcript


#: The operations a full-refresh cadence performs, and the only ones M10
#: replaces. `init_Fast`, `init_part`, `display_Base_color` and
#: `display_Partial` are deliberately absent - PLAN.md M9 decides whether a
#: partial path is built at all, and building one on the vendored window
#: arithmetic is building on sand.
OPERATIONS = ("init", "display", "clear", "sleep")


def write_transcripts(directory: Path | str = TRANSCRIPTS) -> list[Path]:
    """Re-record the specification from the vendored driver."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    written = []
    for name in OPERATIONS:
        path = directory / f"{name}.txt"
        path.write_text(record_vendored(name).text, encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":  # pragma: no cover - the re-recording entry point
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    for written_path in write_transcripts():
        print(written_path)
