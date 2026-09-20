"""The walking skeleton, end to end, in CI.

`tools/render_fixture.py` wires configuration, a source, the view and the
renderer the same way `src/app.py` will at M7. Running it here means the BMP
that PLAN.md M4 exists to produce is not a thing that worked once on a
developer's machine: every commit proves the whole path still walks.

The hostile set matters more than the nominal one. Thirteen entities broken
thirteen different ways must still produce a frame - absence is a state, not a
crash (INTENT.md section 2), and a screen full of placeholders is the correct
output, not a failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from render_fixture import main, parse_args

ROOT = Path(__file__).parent.parent
SETS = ROOT / "tests" / "fixtures" / "sets"
FROZEN = "2026-09-19T12:32:00+00:00"


def run(tmp_path, fixtures=None):
    out = tmp_path / "screen.bmp"
    preview = tmp_path / "preview.bmp"
    code = main(
        [
            "--fixtures",
            str(fixtures or ROOT / "tests" / "fixtures"),
            "--out",
            str(out),
            "--preview",
            str(preview),
            "--at",
            FROZEN,
        ]
    )
    return code, out, preview


class TestTheSkeletonWalks:
    def test_the_recorded_house_renders_a_panel_sized_frame(self, tmp_path):
        code, out, preview = run(tmp_path)

        assert code == 0
        with Image.open(out) as image:
            assert image.size == (800, 480)
            assert image.mode == "RGB"

    def test_it_writes_the_partial_preview_beside_it(self, tmp_path):
        _, _, preview = run(tmp_path)

        with Image.open(preview) as image:
            assert image.size == (800, 480)
            assert image.mode == "1"

    def test_the_frame_actually_has_red_in_it(self, tmp_path):
        """A composite with no red would mean the alert path never ran."""
        _, out, _ = run(tmp_path)

        with Image.open(out) as image:
            assert any(pixel[0] > pixel[1] for pixel in image.convert("RGB").getdata())

    def test_the_preview_has_less_ink_than_the_composite(self, tmp_path):
        """Because everything red is simply missing from it."""
        _, out, preview = run(tmp_path)

        with Image.open(out) as composite, Image.open(preview) as mono:
            coloured = sum(1 for pixel in composite.convert("RGB").getdata() if pixel[0] < 255)
            black = sum(1 for value in mono.convert("L").getdata() if value < 255)

        assert black < coloured

    @pytest.mark.parametrize("name", ["nominal", "hostile"])
    def test_every_fixture_set_produces_a_frame(self, tmp_path, name):
        code, out, _ = run(tmp_path, SETS / name)

        assert code == 0
        assert out.is_file()

    def test_a_house_with_every_sensor_dead_still_fills_the_screen(self, tmp_path):
        """Placeholders and furniture, not a blank panel."""
        _, out, _ = run(tmp_path, SETS / "hostile")

        with Image.open(out) as image:
            inked = sum(1 for value in image.convert("L").getdata() if value < 255)

        assert inked > 1000

    def test_a_missing_fixture_directory_is_reported_not_swallowed(self, tmp_path):
        from sources.port import SourceUnavailable

        with pytest.raises(SourceUnavailable):
            run(tmp_path, tmp_path / "nowhere")


class TestItsArguments:
    def test_it_defaults_to_the_live_capture_and_the_repository_house(self):
        args = parse_args([])

        assert args.fixtures.endswith("tests/fixtures")
        assert args.house.endswith("house.yml")

    def test_a_pinned_timestamp_makes_the_render_reproducible(self, tmp_path):
        """Two runs of the same recording must be the same bytes.

        Without `--at` the frame carries the wall clock and every render
        differs, which would make the BMP useless for diffing a layout change.
        """
        again = tmp_path / "again"
        again.mkdir()

        assert run(tmp_path)[1].read_bytes() == run(again)[1].read_bytes()

    def test_without_a_pinned_timestamp_the_clock_is_now(self, tmp_path):
        """The check above would pass trivially if --at were being ignored."""
        args = parse_args([])

        assert args.at is None
