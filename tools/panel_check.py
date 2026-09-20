"""One operation on the glass, timed - the bench half of PLAN.md M10.6.

A transcript proves that the same bytes leave in the same order. It cannot
prove `spidev`'s chunking of a 48 000-byte `writebytes2`, `gpiozero`'s timing,
or that a BUSY deadline never fires early on a cold panel. Those need the
panel, and this is the smallest thing that puts one operation on it.

It also **measures the milestone's one measurable claim.** The vendored
`ReadBusy()` polls with no delay in the loop, and a first frame under the
systemd unit spent 29.9 s of CPU in 32 s of wall clock (`HARDWARE.md` §4). The
replacement sleeps 10 ms between polls, so the same frame should cost a
fraction of a second of CPU and the same 26 s of wall clock. This prints both,
so the claim is checked rather than asserted.

Run it on the Pi, one operation at a time::

    .venv/bin/python tools/panel_check.py frame
    .venv/bin/python tools/panel_check.py clear

**Wait 180 s between them.** That is the vendor floor (`HARDWARE.md` §3) and
this script has no state to enforce it with - the dashboard's own floor lives
in `refresh/store.py` and belongs to the loop, not to a bench tool.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from config.loader import load_house  # noqa: E402
from refresh.policy import Refresh  # noqa: E402
from render.epd import DRIVER, EPDRenderer  # noqa: E402
from sources.fixture import FixtureSource  # noqa: E402
from view.screen import screen  # noqa: E402

OPERATIONS = ("frame", "clear")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("operation", choices=OPERATIONS)
    parser.add_argument(
        "--fixtures",
        default=str(ROOT / "tests" / "fixtures"),
        help="Recorded payloads to draw, for `frame` (default: the live capture).",
    )
    parser.add_argument("--house", default=str(ROOT / "house.yml"))
    return parser.parse_args(argv)


def run(operation: str, target, items=None) -> tuple[float, float]:
    """Perform one cycle and return (wall seconds, CPU seconds)."""
    wall, cpu = time.monotonic(), time.process_time()

    if operation == "clear":
        target.clear()
    else:
        target.show(items, Refresh.FULL)

    return time.monotonic() - wall, time.process_time() - cpu


def main(argv: list[str] | None = None, target=None) -> int:
    args = parse_args(argv)

    items = None
    if args.operation == "frame":
        config = load_house(args.house)
        items = screen(FixtureSource(config, args.fixtures).fetch())

    target = target or EPDRenderer()
    wall, cpu = run(args.operation, target, items)

    print(f"{args.operation} on {DRIVER}: wall={wall:.1f}s cpu={cpu:.1f}s")
    print("  expected: wall about 26 s (HARDWARE.md section 1), cpu well under 1 s.")
    print("  the vendored driver spent 29.9 s of cpu here (HARDWARE.md section 4).")
    print("  wait 180 s before the next refresh of any class.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
