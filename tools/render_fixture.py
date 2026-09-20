#!/usr/bin/env python3
"""Render a recorded snapshot to BMP, and report what the frame costs.

The development loop of INTENT.md section 7, and the thing PLAN.md M4 exists to
produce: a real 800x480 three-colour BMP on disk that can be looked at. It
wires the same pieces the app will wire at M7 - house configuration, a source,
the view, a renderer - so the walking skeleton walks through every layer rather
than around any of them.

    docker compose run --rm --entrypoint python tools tools/render_fixture.py

Two files come out. The composite is for the eye. The preview is the black
plane alone, which is everything `display_Partial()` can write: read it to see
which parts of the screen a partial refresh simply cannot carry.

The draw list is validated before anything is drawn, so a layout that breaks
the refresh contract fails here rather than on the wall.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config.loader import load_house  # noqa: E402
from render.bmp import BMPRenderer  # noqa: E402
from sources.fixture import FixtureSource  # noqa: E402
from view.drawlist import Colour, UpdateClass, violations  # noqa: E402
from view.screen import screen  # noqa: E402

DEFAULT_OUT = ROOT / "screen.bmp"
DEFAULT_PREVIEW = ROOT / "screen-preview.bmp"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fixtures",
        default=str(ROOT / "tests" / "fixtures"),
        help="Directory of recorded payloads to replay (default: the live capture).",
    )
    parser.add_argument("--house", default=str(ROOT / "house.yml"))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--preview", default=str(DEFAULT_PREVIEW))
    parser.add_argument(
        "--at",
        default=None,
        help="ISO timestamp to stamp the frame with, so a render is reproducible.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    taken_at = datetime.fromisoformat(args.at) if args.at else datetime.now(timezone.utc)
    config = load_house(args.house)
    snapshot = FixtureSource(config, args.fixtures, clock=lambda: taken_at).fetch()

    items = screen(snapshot)
    broken = violations(items)
    if broken:
        print("draw list violates the refresh contract:", file=sys.stderr)
        for line in broken:
            print(f"  {line}", file=sys.stderr)
        return 1

    BMPRenderer().render(items, args.out, args.preview)
    report(snapshot, items, args)
    return 0


def report(snapshot, items, args) -> None:
    """What the frame contains, and what it will cost to refresh.

    The full/partial split is the number PLAN.md M9 has to be decided on: if
    almost every region is full-only, a second init sequence and 8-pixel window
    snapping buy nothing.
    """
    classes = Counter(item.update for item in items)
    red = sorted({item.region for item in items if item.colour is Colour.RED})
    partial_regions = {item.region for item in items if item.update is UpdateClass.PARTIAL}
    full_regions = {item.region for item in items if item.update is UpdateClass.FULL}

    print(f"wrote {args.out} and {args.preview}")
    print(f"rooms: {len(snapshot.rooms)}   items: {len(items)}")
    print(
        f"regions: {len(partial_regions)} partial-eligible, {len(full_regions)} full-only "
        f"({classes[UpdateClass.PARTIAL]} / {classes[UpdateClass.FULL]} items)"
    )
    print(f"red in this frame: {len(red)} regions")
    for region in red:
        print(f"  {region}")

    for error in snapshot.source_errors:
        print(f"source: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
