"""The vendored driver, recorded - and the recording pinned to a file.

PLAN.md M10.1. This is the milestone's foundation and it is worth being
precise about what it does and does not prove. It proves the *sequence*: every
pin write, every SPI byte, every delay, in order, for the four operations a
full-refresh cadence performs. It cannot prove timing, `spidev`'s chunking of a
48 000-byte `writebytes2`, or that the panel likes any of it - PLAN.md M10.6 is
where a human watches the glass.

What that buys is a rewrite proven by diffing two recordings rather than by
reading two files. The transcripts committed under
`tests/fixtures/transcripts/` are recorded from `src/epd7in5b_V2.py`, which
stays in the tree for exactly that purpose, and `tests/test_panel_driver.py`
holds the replacement to the same files.

Nothing in `src/` moves for this file, and the import of the vendored driver
lives inside `panel_harness.vendored_panel()` so that
`tests/test_hardware_boundary.py` stays true.
"""

from __future__ import annotations

import hashlib

import pytest

from tests.panel_harness import (
    BLACK_PLANE,
    OPERATIONS,
    RED_PLANE,
    SPI_OPEN,
    TRANSCRIPTS,
    RecordingConfig,
    Transcript,
    record_vendored,
    vendored_panel,
    write_transcripts,
)


def committed(name: str) -> list[str]:
    return (TRANSCRIPTS / f"{name}.txt").read_text(encoding="utf-8").splitlines()


def digest(data: bytes) -> str:
    return f"write2 {len(data)} sha256={hashlib.sha256(data).hexdigest()}"


def invert(data: bytes) -> bytes:
    return data.translate(bytes(255 - value for value in range(256)))


class TestTheSpecification:
    """Recorded now, and compared with what was recorded then."""

    @pytest.mark.parametrize("name", OPERATIONS)
    def test_the_vendored_driver_still_emits_what_was_committed(self, name):
        assert record_vendored(name).lines == committed(name)

    @pytest.mark.parametrize("name", OPERATIONS)
    def test_the_transcript_is_not_empty(self, name):
        """A recorder that silently stopped recording would pass every
        comparison above."""
        assert len(committed(name)) > 5

    def test_re_recording_reproduces_the_committed_files(self, tmp_path):
        """The one documented way to take an upstream fix: re-record, diff."""
        for path in write_transcripts(tmp_path):
            assert path.read_text(encoding="utf-8") == (TRANSCRIPTS / path.name).read_text(
                encoding="utf-8"
            )


class TestWhatTheTranscriptSays:
    """The sequences themselves, asserted where they carry meaning.

    Not a second copy of the files - these are the handful of facts
    `render/panel/driver.py` is written from, stated where a reader can check
    them against HARDWARE.md section 4 without decoding hex.
    """

    def test_init_opens_the_bus_resets_the_panel_and_waits_for_it(self):
        lines = committed("init")

        assert lines[:2] == ["pin PWR 1", SPI_OPEN]
        # The reset pulse of HARDWARE.md section 5: high, low for 4 ms, high.
        assert lines[2:8] == [
            "pin RST 1",
            "delay 200",
            "pin RST 0",
            "delay 4",
            "pin RST 1",
            "delay 200",
        ]
        # 0x04 is POWER_ON, and the driver waits on BUSY before configuring.
        assert "write 04" in lines
        assert "read BUSY 1" in lines

    def test_display_writes_black_to_0x10_and_red_to_0x13_then_refreshes(self):
        """HARDWARE.md section 4's table, as bytes rather than as prose."""
        lines = committed("display")
        commands = [line for line in lines if line.startswith("write ")]
        bulk = [line for line in lines if line.startswith("write2 ")]

        assert commands == ["write 10", "write 13", "write 12", "write 71"]
        assert len(bulk) == 2
        assert lines.index("write 10") < lines.index(bulk[0]) < lines.index("write 13")
        # 0x12 is DISPLAY_REFRESH, and the 26 seconds are spent inside the
        # BUSY wait that follows it.
        assert lines[-6:] == [
            "write 12",
            "delay 100",
            "pin DC 0",
            "write 71",
            "read BUSY 1",
            "delay 200",
        ]

    def test_the_double_inversion_leaves_black_as_pil_drew_it(self):
        """`getbuffer()` inverts every byte and `display()` inverts the black
        buffer back, so what reaches `0x10` is the plane PIL produced and what
        reaches `0x13` is its negative. Reimplementing either half is how this
        gets broken, which is why both are pinned here."""
        bulk = [line for line in committed("display") if line.startswith("write2 ")]

        assert bulk[0] == digest(BLACK_PLANE.tobytes("raw"))
        assert bulk[1] == digest(invert(RED_PLANE.tobytes("raw")))

    def test_the_two_planes_are_not_the_same_bytes(self):
        """So that a driver sending one plane twice cannot pass."""
        bulk = [line for line in committed("display") if line.startswith("write2 ")]

        assert bulk[0] != bulk[1]

    def test_clear_blanks_both_planes(self):
        lines = committed("clear")
        bulk = [line for line in lines if line.startswith("write2 ")]

        assert [line for line in lines if line.startswith("write ")] == [
            "write 10",
            "write 13",
            "write 12",
            "write 71",
        ]
        assert bulk == [digest(b"\xff" * 48000), digest(b"\x00" * 48000)]

    def test_sleep_powers_the_panel_down_and_releases_nothing(self):
        """`module_exit(cleanup=False)`: the SPI device closes and the pins go
        low, but the `gpiozero` objects are never released. That is deliberate
        here - the process keeps its claim between cycles - and it is why the
        replacement grows an explicit `close()` on top (PLAN.md M10.2)."""
        lines = committed("sleep")

        assert "write 02" in lines  # POWER_OFF
        assert "write 07" in lines  # DEEP_SLEEP
        assert "write a5" in lines  # its one argument
        assert lines[-5:] == [
            "delay 2000",
            "spi close",
            "pin RST 0",
            "pin DC 0",
            "pin PWR 0",
        ]
        assert "release" not in lines


class TestTheRecorderIsFaithful:
    """A recorder that recorded the wrong thing would pin the wrong spec."""

    def test_chip_select_reaches_no_pin(self):
        """`send_command()` toggles CS around every byte and
        `RaspberryPi.digital_write()` has that branch commented out, so the
        toggles go nowhere. Recording the effect rather than the call is what
        lets a driver that never mentions CS match this transcript - and it is
        faithful, because spidev drives CE0 itself."""
        transcript = Transcript()
        config = RecordingConfig(transcript)

        config.digital_write(config.CS_PIN, 0)
        config.digital_write(config.CS_PIN, 1)

        assert transcript.lines == []
        assert "pin CS" not in "\n".join(committed("init"))

    def test_reading_any_pin_but_busy_is_the_error_the_vendored_code_makes(self):
        """`self.RST_PIN.value`, where `RST_PIN` is the integer 17. Three dead
        branches; nothing in the driver reaches them."""
        config = RecordingConfig(Transcript())

        with pytest.raises(AttributeError):
            config.digital_read(config.RST_PIN)

    def test_the_busy_pin_can_be_scripted_so_the_loop_terminates(self):
        """`ReadBusy()` has no timeout, so a recorder with a pin stuck at 0
        would hang the suite the way a dead panel hangs the dashboard."""
        transcript = record_vendored("sleep", busy=(0, 0, 0, 1))
        reads = [line for line in transcript.lines if line.startswith("read ")]

        assert reads[:4] == ["read BUSY 0", "read BUSY 0", "read BUSY 0", "read BUSY 1"]

    def test_the_vendored_busy_loop_spins_with_no_delay_in_it(self):
        """HARDWARE.md section 4's measured figure, as a structural fact: 29.9 s
        of CPU in a 32 s cycle because this loop never sleeps. The replacement
        does, which is the one place its transcript is allowed to differ."""
        lines = record_vendored("sleep", busy=(0, 0, 0, 1)).lines
        first = lines.index("read BUSY 0")
        last = lines.index("read BUSY 1")

        assert [line for line in lines[first:last] if line.startswith("delay")] == []

    def test_a_fresh_driver_is_imported_for_every_recording(self):
        """The driver builds its `epdconfig` at module scope, so a cached
        import would hand the second recording the first one's recorder."""
        first, second = Transcript(), Transcript()

        with vendored_panel(first) as one, vendored_panel(second) as two:
            one.reset()
            two.reset()

        assert len(first.lines) == len(second.lines) == 6

    def test_the_import_does_not_outlive_the_fixture(self):
        """AGENTS.md: nothing may assume hardware. Leaving `epdconfig` in
        `sys.modules` would let a later test import the driver by accident and
        pass for the wrong reason."""
        import sys

        with vendored_panel(Transcript()):
            assert "epdconfig" in sys.modules

        assert "epdconfig" not in sys.modules
        assert "epd7in5b_V2" not in sys.modules
