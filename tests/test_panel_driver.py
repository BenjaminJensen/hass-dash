"""The replacement, held to the vendored driver's own transcript.

PLAN.md M10.3. The first class here is the milestone's exit condition: for
every full-refresh operation, `render/panel/driver.py` emits exactly what
`src/epd7in5b_V2.py` emits - same commands, same order, same bytes, same
delays, against the files committed in `tests/fixtures/transcripts/`. Both
sides are compared with the same recording, so neither can drift without the
other noticing.

The rest of the file is the other half of the bargain: **every deliberate
difference is a named assertion**, stated here rather than discovered on a
wall. There are six of them and each one is a defect the vendored file has.

What none of this can prove is in M10.6, and it is worth naming: `spidev`'s
chunking of a 48 000-byte `writebytes2`, `gpiozero`'s timing, and whether a
deadline ever fires early on a cold panel. Those need the glass.
"""

from __future__ import annotations

import pytest

from render.panel.driver import BUSY_TIMEOUT_S, INVERT, PLANE_BYTES, POLL_MS, Panel
from render.panel.errors import PanelError
from render.panel.transport import Pin
from tests.panel_harness import (
    BLACK_PLANE,
    OPERATIONS,
    RED_PLANE,
    RecordingTransport,
    Transcript,
    record_panel,
    record_vendored,
)
from tests.test_panel_transcript import committed


def panel(busy=(1,), **kwargs) -> tuple[Panel, Transcript]:
    transcript = Transcript()
    return Panel(RecordingTransport(transcript, busy), **kwargs), transcript


class TestItEmitsWhatTheVendoredDriverEmits:
    """The exit condition, stated four times."""

    @pytest.mark.parametrize("name", OPERATIONS)
    def test_the_transcript_matches_the_committed_recording(self, name):
        assert record_panel(name).lines == committed(name)

    @pytest.mark.parametrize("name", OPERATIONS)
    def test_the_two_drivers_agree_with_each_other_right_now(self, name):
        """Belt and braces: the committed file could in principle be stale for
        both. This one compares the two implementations directly."""
        assert record_panel(name).lines == record_vendored(name).lines

    def test_a_busy_panel_produces_the_same_wire_sequence(self):
        """With the poll delays taken out, a panel that makes the driver wait
        four times produces the same commands and reads on both sides. The
        delays are the one difference, and they are asserted below."""
        ours = record_panel("sleep", busy=(0, 0, 0, 1)).lines
        theirs = record_vendored("sleep", busy=(0, 0, 0, 1)).lines

        assert [line for line in ours if line != f"delay {POLL_MS:g}"] == theirs


class TestTheBusyWaitIsTheReasonThisExists:
    """The vendored loop has no timeout and no delay. Both are fixed here, and
    the fix is the milestone's whole justification (PLAN.md M10)."""

    def test_a_panel_that_never_answers_raises_instead_of_hanging(self):
        """The worst failure the vendored file has: `Restart=always` cannot
        help, because the unit is still running. The wall silently keeps
        yesterday's frame and the journal says nothing."""
        clock = iter([0.0, 10.0, 20.0, 30.0, 41.0, 41.0, 41.0])
        driver, _ = panel(busy=(0,), monotonic=lambda: next(clock))

        with pytest.raises(PanelError) as error:
            driver.sleep()

        assert "BUSY" in str(error.value)
        assert "40" in str(error.value)

    def test_the_failure_is_the_type_the_loop_already_knows_how_to_survive(self):
        """`PanelError` means the cycle did not happen: the floor, the
        keep-alive and the partial budget are untouched and the next tick
        tries again."""
        assert issubclass(PanelError, RuntimeError)

    def test_it_sleeps_between_polls_rather_than_spinning(self):
        """29.9 s of CPU in a 32 s cycle, measured on the board
        (HARDWARE.md section 4), because the vendored loop never yields."""
        transcript = record_panel("sleep", busy=(0, 0, 0, 1))
        polls = [line for line in transcript.lines if line == f"delay {POLL_MS:g}"]

        assert len(polls) == 3

    def test_the_poll_interval_is_negligible_against_a_refresh(self):
        """10 ms on a 26 000 ms refresh, and ~2 600 polls instead of ~430 000."""
        assert POLL_MS == 10
        assert POLL_MS / 1000 * 2600 < 30

    def test_the_deadline_sits_between_a_refresh_and_the_units_stop_timeout(self):
        """Past 26 s so a healthy panel is never cut off; inside the unit's
        `TimeoutStopSec=45s` so a hung one raises before systemd starts
        killing things."""
        assert 26 < BUSY_TIMEOUT_S < 45

    def test_a_panel_that_answers_late_still_succeeds(self):
        clock = iter([0.0] + [1.0] * 20)
        driver, transcript = panel(busy=(0, 0, 0, 0, 1), monotonic=lambda: next(clock))

        driver.sleep()

        assert transcript.lines[-1] == "pin PWR 0"


class TestTheDeliberateDifferences:
    """Six of them. Each is a defect in the file this one replaces."""

    def test_the_callers_buffer_is_never_mutated(self):
        """The vendored `display()` inverts `imageblack` in place, so the same
        buffer sent twice draws its own negative the second time. Nothing does
        that today; a retry written later would, and it would look like a
        driver fault rather than a caller one."""
        driver, transcript = panel()
        black = driver.buffer(BLACK_PLANE)
        red = driver.buffer(RED_PLANE)
        before = bytes(black)

        driver.display(black, red)
        driver.display(black, red)

        assert black == before
        bulk = [line for line in transcript.lines if line.startswith("write2 ")]
        assert bulk[0] == bulk[2], "the same buffer sent twice sent different bytes"

    def test_the_buffer_is_immutable(self):
        """`bytes`, not `bytearray`, so in-place inversion is not available to
        anybody - including a future version of this file."""
        driver, _ = panel()

        assert isinstance(driver.buffer(BLACK_PLANE), bytes)
        assert not isinstance(driver.buffer(BLACK_PLANE), bytearray)

    def test_the_inversion_is_a_translate_and_gives_the_same_answer(self):
        """90x faster than the Python `for` loop it replaces - 0.326 ms against
        29.3 ms per plane on this board, three planes per frame - and the
        result is asserted against the definition rather than trusted."""
        driver, _ = panel()
        raw = BLACK_PLANE.tobytes("raw")

        assert driver.buffer(BLACK_PLANE) == bytes(byte ^ 0xFF for byte in raw)
        assert INVERT[0] == 255 and INVERT[255] == 0

    def test_a_frame_the_wrong_size_raises_instead_of_going_blank(self):
        """`getbuffer()` answers a size it does not recognise with a warning
        and a blank buffer, which reaches the wall as a cleared screen and
        nothing in the log. A blank dashboard looks like a quiet house."""
        from PIL import Image

        driver, _ = panel()

        with pytest.raises(PanelError) as error:
            driver.buffer(Image.new("1", (400, 300), 255))

        assert "(400, 300)" in str(error.value)

    def test_a_plane_of_the_wrong_length_never_reaches_the_bus(self):
        """It would leave the panel part-way through a transfer, waiting for
        bytes that are not coming."""
        driver, transcript = panel()

        with pytest.raises(PanelError) as error:
            driver.display(b"\x00" * 10, b"\x00" * PLANE_BYTES)

        assert "black" in str(error.value)
        assert transcript.lines == []

    def test_chip_select_is_never_driven(self):
        """`spidev` drives CE0 as part of every transfer, and the vendored
        `digital_write()` has its CS branch commented out - so the vendored
        toggles have never reached a pin either. Dropping them changes the
        transcript not at all, which is why this is safe rather than brave."""
        assert [pin.value for pin in Pin] == ["RST", "DC", "PWR"]
        assert "CS" not in "\n".join(record_panel("init").lines)

    def test_clear_sends_two_transfers_rather_than_ninety_six_thousand(self):
        """`display_Base_color()` sends one byte per SPI transaction, each with
        four pin writes. It is not ported; `clear()` uses the whole-buffer path
        the vendored `Clear()` already used."""
        transcript = record_panel("clear")

        assert len([line for line in transcript.lines if line.startswith("write2 ")]) == 2
        assert len(transcript.lines) < 20


class TestWhatIsNotHere:
    """The partial path, named as absent rather than left to be assumed."""

    @pytest.mark.parametrize(
        "name", ["init_part", "init_Fast", "display_Partial", "display_Base_color"]
    )
    def test_no_partial_or_flat_fill_path_was_ported(self, name):
        """PLAN.md M9 decides whether a partial path is built at all, and the
        vendored window arithmetic it would be built on truncates rather than
        rounds (HARDWARE.md section 4). Porting it would be building on sand."""
        driver, _ = panel()

        assert not hasattr(driver, name)


class TestTheLifecycle:
    """Three calls where the vendored config has two."""

    def test_sleep_powers_the_module_down_but_keeps_the_pins(self):
        """`module_exit(cleanup=False)`: the process keeps its claim between
        refreshes, which is what lets the next `init()` work at all."""
        driver, transcript = panel()

        driver.sleep()

        assert transcript.lines[-4:] == ["spi close", "pin RST 0", "pin DC 0", "pin PWR 0"]
        assert "release" not in transcript.lines

    def test_close_is_the_thing_the_vendored_code_has_no_equivalent_for(self):
        """`module_exit(cleanup=False)` never closes the `gpiozero` devices, so
        nothing in the vendored path can give the pins back."""
        driver, transcript = panel()

        driver.close()

        assert transcript.lines == ["release"]

    def test_the_panel_states_its_own_size(self):
        """`EPDRenderer` measures the frame against these before waking
        anything, so they are part of the surface, not a detail."""
        driver, _ = panel()

        assert (driver.width, driver.height) == (800, 480)
        assert PLANE_BYTES == 800 // 8 * 480

    def test_constructing_a_panel_claims_nothing(self):
        """The transport decides whether it owns hardware. This is the
        distinction the vendored file collapses, and it is why every sequence
        above can be asserted in a container with no SPI bus."""
        transcript = Transcript()

        Panel(RecordingTransport(transcript))

        assert transcript.lines == []
