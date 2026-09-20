"""The composition root, and the loop that drives the panel.

Everything below this file is a pure function or a single-purpose object with
its dependencies handed to it. This is the one module that decides *which*
config, *which* source, *which* renderer and *which* clocks - which is what a
composition root is for, and why it is the only place in the project that knows
all of them exist at once.

**The order of a cycle is the argument.** Decide, then fetch, then render:

1. `refresh.policy.decide()` answers "is anything happening this tick", from
   two clocks and what happened last time. It does not look at the data, and
   INTENT.md section 4 is explicit about why - red lags on purpose, so a value
   crossing into alert does not accelerate anything.
2. Only if something *is* happening does the source get asked for a snapshot.
   A loop that fetched every tick would wake Home Assistant 120 times an hour
   to be told to do nothing, and would smear the readings across the wait.
3. The draw list is validated, rendered, and only then is the refresh recorded.
   `record()` is called on a refresh that reached the glass, never on the
   strength of the decision alone.

**A source failure never blanks the screen.** INTENT.md section 2: the last
good frame is always better than no frame. So an unreachable instance leaves
the previous frame's draw list in place and the cycle redraws *that* - with its
original timestamp, because the header says when the data is from and
re-stamping a stale frame with the current time would be a lie the wall tells
at a glance. The frame visibly ages, which is exactly the signal a person
needs. Per-entity failure never gets this far; it arrives as `None` in the
snapshot and a line in `source_errors` (see `sources/port.py`).

**Two clocks, because the target has two.** Wall time for "what time is it",
`time.monotonic()` for "how long has it been" - the board has no RTC and
HARDWARE.md section 6 is explicit about the consequence. Both are injectable,
which is what lets the loop run a simulated day in a test without sleeping
through it. `run()` also takes the `RefreshState` it starts from, which is the
seam PLAN.md M8.4 hangs a persisted `last_full_at` on so a restart cannot lose
the 24 h keep-alive.

**What is still a placeholder.** The dirty set is "every region of the last
frame, by its update class" rather than a diff of two draw lists. A real diff
belongs in `render/` (INTENT.md section 6) and PLAN.md M9 builds it against
8-aligned windows. Until then the placeholder is nearly true anyway, because
the updated-at clock changes every minute and it lives in a partial region.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from config.loader import ConfigError, load_house
from domain.format_da import LOCAL_TZ
from domain.models import Snapshot
from refresh.policy import (
    DEFAULT_POLICY,
    Dirty,
    Policy,
    Refresh,
    RefreshState,
    decide,
    record,
)
from render.bmp import BMPRenderer
from sources.fixture import FixtureSource
from sources.homeassistant import HomeAssistantSource
from sources.port import SourceUnavailable
from view.drawlist import DrawItem, UpdateClass, violations
from view.screen import screen

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_HOUSE = ROOT / "house.yml"
DEFAULT_FIXTURES = ROOT / "tests" / "fixtures"
DEFAULT_OUT = ROOT / "screen.bmp"
DEFAULT_ENV = ROOT / ".env"

#: How often the loop wakes to ask the policy. Deciding is arithmetic on two
#: numbers, so a wasted wake costs nothing; the expensive things - the fetch and
#: the 26-second refresh - only happen when the answer is yes. Half a minute is
#: fine enough to hit a five-minute partial cycle on time.
TICK_SECONDS = 30.0

#: Where the credentials come from. Named here rather than in `sources/` so
#: that the adapter takes a URL and a token and has no opinion about where a
#: deployment keeps them.
URL_VAR = "HASS_URL"
TOKEN_VAR = "HASS_TOKEN"

SOURCES = ("fixture", "hass")
TARGETS = ("bmp", "epd")

logger = logging.getLogger("dash")


class ConfigurationError(Exception):
    """The app was launched in a way that cannot work.

    Distinct from `config.loader.ConfigError`, which is a bad `house.yml`, and
    from `SourceUnavailable`, which is a runtime state the loop survives. This
    one is a wrong command line or a missing credential: there is nothing to
    retry, so it is reported once and the process exits.
    """


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


class RenderTarget(Protocol):
    """Somewhere a draw list can be put. A file today, the panel at M8."""

    #: Short identifier for logs, so a line says where a frame went.
    name: str

    def show(self, items: tuple[DrawItem, ...], refresh: Refresh) -> None:
        """Put this frame on the target, as this class of refresh."""
        ...


class BMPTarget:
    """Writes the frame to disk, per INTENT.md section 7.

    Two files: the three-colour composite for the eye, and the black plane
    alone as the preview of what a partial-only refresh can carry.

    `refresh` is accepted and ignored, and that is not laziness. A partial
    refresh on the panel writes changed black regions onto whatever red the
    glass is already holding; a file has no memory of the frame before it, so
    there is nothing here for the distinction to mean. It becomes real when M9
    builds the partial path, and the parameter is in the signature now so that
    `EPDRenderer` is a drop-in rather than a change to the loop.
    """

    def __init__(
        self,
        out: str | Path = DEFAULT_OUT,
        preview: str | Path | None = None,
        renderer: Any = None,
    ) -> None:
        self.out = Path(out)
        self.preview = Path(preview) if preview is not None else preview_path(self.out)
        self.renderer = renderer or BMPRenderer()

    @property
    def name(self) -> str:
        return f"bmp:{self.out.name}"

    def show(self, items: tuple[DrawItem, ...], refresh: Refresh) -> None:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.renderer.render(items, self.out, self.preview)


def preview_path(out: Path) -> Path:
    """`screen.bmp` -> `screen-preview.bmp`, beside it."""
    return out.with_name(f"{out.stem}-preview{out.suffix}")


# ---------------------------------------------------------------------------
# The frame on the glass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    """The last draw list that reached the target, and where it came from.

    Held for two reasons: it is the last good frame the fallback redraws, and
    its regions are the placeholder dirty set the next decision is made
    against.
    """

    snapshot: Snapshot | None = None
    items: tuple[DrawItem, ...] = ()

    @property
    def dirty(self) -> Dirty:
        """Which regions to call changed - the placeholder M9 replaces.

        Everything that was drawn last time, split by the update class the
        layout declared for it. It over-reports, and the direction of the error
        is the safe one: a region named dirty that did not change costs a
        redraw inside a refresh that was going to happen anyway, whereas one
        missed would sit stale on the wall until the next full cycle.
        """
        return Dirty(
            partial=frozenset(
                item.region for item in self.items if item.update is UpdateClass.PARTIAL
            ),
            full=frozenset(item.region for item in self.items if item.update is UpdateClass.FULL),
        )


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def read_env_file(path: str | Path) -> dict[str, str]:
    """The `KEY=value` lines of a `.env` file, or nothing if there is none.

    Deliberately small and deliberately not a dependency: comments, blank
    lines, a leading `export`, and one layer of matching quotes. A missing file
    is not an error - a deployment may keep its credentials in the environment
    and never write one - so this returns an empty mapping rather than raising.
    Whether the values it did not find are *required* is `build_source()`'s
    question, and only for the live source.
    """
    values: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return values

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()

        name, separator, value = line.partition("=")
        if not separator:
            continue
        values[name.strip()] = _unquote(value.strip())

    return values


def settings(env_path: str | Path, environ: dict[str, str] | None = None) -> dict[str, str]:
    """The `.env` file, with the real environment winning over it.

    That precedence and not the other one: the file is the checked-in default
    for a workstation, and a systemd unit or a shell that exports a variable is
    stating an intention about *this* run. The surprising direction would be a
    file on disk quietly overruling it.
    """
    merged = read_env_file(env_path)
    merged.update(environ if environ is not None else os.environ)
    return merged


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


# ---------------------------------------------------------------------------
# Building the pieces
# ---------------------------------------------------------------------------


def build_source(kind: str, config: Any, fixtures: str | Path, env: dict[str, str]) -> Any:
    """The source named on the command line, or a clear reason it cannot be."""
    if kind == "fixture":
        return FixtureSource(config, fixtures)

    if kind != "hass":
        raise ConfigurationError(f"unknown source {kind!r}; choose one of {', '.join(SOURCES)}")

    url = env.get(URL_VAR, "").strip()
    token = env.get(TOKEN_VAR, "").strip()

    missing = [name for name, value in ((URL_VAR, url), (TOKEN_VAR, token)) if not value]
    if missing:
        raise ConfigurationError(
            f"{' and '.join(missing)} must be set to use the live source. "
            f"Put them in {DEFAULT_ENV.name} or export them."
        )

    # The retired client wanted the suffix and this one appends `/api/states`
    # itself, so a carried-over value produces `/api/api/states` - a 404 that
    # reads like a broken instance rather than a broken setting. Refused at
    # startup with the fix in the message (PLAN.md M8).
    if url.rstrip("/").endswith("/api"):
        raise ConfigurationError(
            f"{URL_VAR} must not end in /api - the adapter appends it. "
            f"Use {url.rstrip('/')[: -len('/api')] or '/'} instead."
        )

    return HomeAssistantSource(config, url, token)


def build_target(kind: str, out: str | Path) -> RenderTarget:
    """The target named on the command line, or a clear reason it cannot be."""
    if kind == "bmp":
        return BMPTarget(out)

    if kind == "epd":
        raise ConfigurationError(
            "--target epd needs EPDRenderer, which PLAN.md M8 builds. "
            "Nothing in this container can drive the panel: use --target bmp."
        )

    raise ConfigurationError(f"unknown target {kind!r}; choose one of {', '.join(TARGETS)}")


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def run(
    source: Any,
    target: RenderTarget,
    policy: Policy = DEFAULT_POLICY,
    state: RefreshState | None = None,
    ticks: int | None = None,
    tick_seconds: float = TICK_SECONDS,
    now: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    frame: Frame | None = None,
) -> int:
    """Drive the panel until `ticks` cycles have passed, or forever.

    `ticks` is how many times the loop wakes, not how many frames it draws:
    most wakes decide to do nothing. `ticks=1` is `--once`, and with a fresh
    `RefreshState` that first decision is always a full refresh, so one tick is
    one frame.

    Returns 0 if every cycle that meant to draw did, and 1 if any of them
    failed - which for `--once` is the exit code of a render.
    """
    now = now or _local_now
    monotonic = monotonic or time.monotonic
    sleep = sleep or time.sleep

    state = state or RefreshState()
    frame = frame or Frame()
    last_reason: Any = None
    last_errors: tuple[str, ...] = ()
    failures = 0
    woken = 0

    while ticks is None or woken < ticks:
        woken += 1
        decision = decide(now(), monotonic(), state, frame.dirty, policy)

        if not decision.refreshes:
            # Logged only when the answer *changes*, so entering quiet hours is
            # one line and staying in them is none. A NONE decision every 30 s
            # would bury the refreshes it is meant to explain.
            if decision.reason is not last_reason:
                logger.info(_kv(refresh="none", reason=decision.reason.value))
            last_reason = decision.reason
            _wait(sleep, tick_seconds, woken, ticks)
            continue

        last_reason = decision.reason

        try:
            snapshot: Snapshot | None = source.fetch()
            stale = False
        except SourceUnavailable as error:
            snapshot, stale = frame.snapshot, True
            # `down`, not the word the exception is named for: that word is a
            # Home Assistant state value and the boundary test is right to
            # object to it appearing up here (INTENT.md section 2).
            logger.warning(_kv(source=source.name, down=error))

        if snapshot is None:
            # The source failed and there has never been a good frame. There is
            # nothing to fall back to and nothing to draw; the next tick tries
            # again rather than putting confident placeholders on the wall.
            failures += 1
            _wait(sleep, tick_seconds, woken, ticks)
            continue

        last_errors = _log_source_errors(snapshot, last_errors)

        # A stale cycle redraws the frame it already has - same draw list, same
        # timestamp in the header. Recomputing it from the old snapshot would
        # give the same answer more slowly.
        items = frame.items if stale else screen(snapshot)

        broken = violations(items)
        if broken:
            # A layout that breaks the refresh contract is a developer error,
            # not a runtime state, and it must not reach the glass. The loop
            # survives it so that a bad region cannot take the wall down.
            for line in broken:
                logger.error(_kv(contract=line))
            failures += 1
            _wait(sleep, tick_seconds, woken, ticks)
            continue

        started = monotonic()
        try:
            target.show(items, decision.refresh)
        except Exception:
            logger.exception(_kv(target=target.name, failed=decision.refresh.value))
            failures += 1
            _wait(sleep, tick_seconds, woken, ticks)
            continue

        # After the write, not before it: the floor counts from when the panel
        # finished, and a full refresh spends 26 of its seconds inside `show()`.
        finished = monotonic()
        state = record(state, decision, now(), finished)
        frame = Frame(snapshot, items)

        logger.info(
            _kv(
                refresh=decision.refresh.value,
                reason=decision.reason.value,
                # Omitted rather than logged as zero, because zero is what the
                # first frame honestly has: nothing changed, there was nothing
                # there before.
                changed=len(decision.regions) or None,
                source=source.name,
                target=target.name,
                stale=stale or None,
                errors=len(snapshot.source_errors) or None,
                ms=round((finished - started) * 1000),
            )
        )

        _wait(sleep, tick_seconds, woken, ticks)

    return 1 if failures else 0


def _wait(sleep: Callable[[float], None], seconds: float, woken: int, ticks: int | None) -> None:
    """Sleep between cycles, but never after the last one.

    So that `--once` returns as soon as the frame is written rather than
    holding the process open for a tick it will not use.
    """
    if ticks is None or woken < ticks:
        sleep(seconds)


def _log_source_errors(snapshot: Snapshot, previous: tuple[str, ...]) -> tuple[str, ...]:
    """Report what the source could not fetch, when it changes.

    A renamed entity shows a placeholder forever until a human fixes the
    config, so it has to be visible - but repeating the same three lines every
    five minutes is how a log stops being read. Logged on change, which turns
    "this is still broken" into "this broke" and "this was fixed".
    """
    current = tuple(snapshot.source_errors)
    if current != previous:
        for line in current:
            logger.warning(_kv(source_error=line))
    return current


def _local_now() -> datetime:
    """Wall time in the household's zone (INTENT.md section 2: Danish, locally).

    Aware, and in `Europe/Copenhagen` specifically, because quiet hours and the
    morning window are read off `now.time()` and a UTC reading would move them
    by an hour twice a year.
    """
    return datetime.now(LOCAL_TZ)


def _kv(**fields: Any) -> str:
    """One log line as `key=value` pairs, skipping the ones with nothing to say.

    Structured enough to grep out of `journalctl` and short enough to read on a
    terminal, which is the whole requirement here.
    """
    return " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dash",
        description="Render the house to an e-paper panel, or to a BMP on disk.",
    )
    parser.add_argument(
        "--source",
        choices=SOURCES,
        default="fixture",
        help="Where a snapshot comes from (default: the recorded fixtures).",
    )
    parser.add_argument(
        "--target",
        choices=TARGETS,
        default="bmp",
        help="Where a frame goes (default: a BMP on disk).",
    )
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="BMP target: where to write.")
    parser.add_argument("--house", default=str(DEFAULT_HOUSE))
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--env", default=str(DEFAULT_ENV))
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log every decision, including the ones to do nothing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        config = load_house(args.house)
        source = build_source(args.source, config, args.fixtures, settings(args.env))
        target = build_target(args.target, args.out)
    except (ConfigError, ConfigurationError) as error:
        # Both are "this cannot work as launched", and neither is worth a
        # traceback: the message is the whole content.
        logger.error(_kv(startup=error))
        return 2

    logger.info(_kv(started=source.name, target=target.name, once=args.once or None))

    try:
        return run(source, target, ticks=1 if args.once else None)
    except KeyboardInterrupt:
        logger.info(_kv(stopped="interrupt"))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
