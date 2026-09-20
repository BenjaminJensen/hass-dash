"""The composition root, and a day of the loop run in milliseconds.

Two things are worth testing here and they are different in kind.

*The wiring* - that `--source fixture --target bmp --once` produces a real BMP
through config, source, view and renderer with nothing stubbed. That is
PLAN.md M7's exit condition and it is an end-to-end test on purpose: every
layer below has its own suite, and what this one proves is that they were
plugged into each other correctly.

*The loop* - that driving the panel from `refresh.policy` actually obeys it. The
policy was proved as a pure function at M6; what is unproven until here is that
the loop calls it with the right clocks, records only refreshes that happened,
and never fetches on a tick that decided to do nothing. So the clocks are
injected, a simulated day passes in a few thousand cheap iterations, and the
vendor's limits are asserted over what the *loop* did rather than over what the
policy said.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from app import (
    BMPTarget,
    ConfigurationError,
    Frame,
    build_source,
    build_target,
    main,
    preview_path,
    read_env_file,
    run,
    settings,
)
from config.loader import load_house
from domain.format_da import LOCAL_TZ
from domain.models import Snapshot
from refresh.policy import DEFAULT_POLICY, FLOOR_SECONDS, MAX_PARTIALS, Refresh, RefreshState
from sources.fixture import FixtureSource
from sources.port import SourceUnavailable
from view.drawlist import UpdateClass

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
SETS = FIXTURES / "sets"
HOUSE = ROOT / "house.yml"

TICK = 30.0
MIDNIGHT = datetime(2026, 3, 10, 0, 0, tzinfo=LOCAL_TZ)
MID_MORNING = datetime(2026, 3, 10, 10, 0, tzinfo=LOCAL_TZ)
DAY_OF_TICKS = int(24 * 3600 / TICK)


@pytest.fixture
def config():
    return load_house(HOUSE)


class FakeClock:
    """Wall time and a monotonic reading that only move when the loop sleeps.

    The two advance together here, which is the *uninteresting* case - the M6
    suite is where they are driven apart. What this one needs is a day that
    passes without one.
    """

    def __init__(self, start: datetime = MIDNIGHT):
        self.wall = start
        self.mono = 0.0

    def now(self) -> datetime:
        return self.wall

    def monotonic(self) -> float:
        return self.mono

    def sleep(self, seconds: float) -> None:
        self.wall += timedelta(seconds=seconds)
        self.mono += seconds


class CountingSource:
    """A real fixture source with a turnstile on it, and a kill switch."""

    name = "counting"

    def __init__(self, inner, fail_after: int | None = None):
        self.inner = inner
        self.fail_after = fail_after
        self.fetches = 0

    def fetch(self) -> Snapshot:
        self.fetches += 1
        if self.fail_after is not None and self.fetches > self.fail_after:
            raise SourceUnavailable("the instance is not answering")
        return self.inner.fetch()


class DeadSource:
    """Never produces anything. The first-run-with-no-network case."""

    name = "dead"

    def __init__(self):
        self.fetches = 0

    def fetch(self) -> Snapshot:
        self.fetches += 1
        raise SourceUnavailable("nothing here")


class RecordingTarget:
    """Records what it was shown and when, and draws nothing.

    No PIL: this suite asks whether the loop obeys the contract, and executing
    a draw list into two planes 190 times would make a simulated day cost
    seconds without testing anything `test_render_bmp.py` does not.
    """

    name = "recording"

    def __init__(self, clock: FakeClock, fail: bool = False):
        self.clock = clock
        self.fail = fail
        self.shown: list[tuple[datetime, float, Refresh, tuple]] = []

    def show(self, items, refresh: Refresh) -> None:
        if self.fail:
            raise OSError("no space left on device")
        self.shown.append((self.clock.now(), self.clock.monotonic(), refresh, items))

    @property
    def fulls(self):
        return [entry for entry in self.shown if entry[2] is Refresh.FULL]

    @property
    def partials(self):
        return [entry for entry in self.shown if entry[2] is Refresh.PARTIAL]


def simulate(config, ticks=DAY_OF_TICKS, start=MIDNIGHT, fail_after=None, source=None):
    """Run the loop over a fast-forwarded clock and hand back what happened."""
    clock = FakeClock(start)
    source = source or CountingSource(FixtureSource(config, FIXTURES), fail_after)
    target = RecordingTarget(clock)
    code = run(
        source,
        target,
        ticks=ticks,
        tick_seconds=TICK,
        now=clock.now,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return code, clock, source, target


class TestTheSkeletonIsNowAnApplication:
    """PLAN.md M7's exit condition, with nothing stubbed."""

    def test_once_renders_the_screen(self, tmp_path):
        out = tmp_path / "screen.bmp"

        code = main(["--source", "fixture", "--target", "bmp", "--once", "--out", str(out)])

        assert code == 0
        with Image.open(out) as image:
            assert image.size == (800, 480)
            assert image.mode == "RGB"

    def test_it_writes_the_partial_preview_beside_it(self, tmp_path):
        out = tmp_path / "screen.bmp"

        main(["--once", "--out", str(out)])

        with Image.open(tmp_path / "screen-preview.bmp") as image:
            assert image.size == (800, 480)
            assert image.mode == "1"

    def test_the_defaults_are_the_development_loop(self):
        """`--source fixture --target bmp` is what you get for typing nothing."""
        from app import parse_args

        args = parse_args([])

        assert (args.source, args.target, args.once) == ("fixture", "bmp", False)

    def test_a_hostile_fixture_set_still_produces_a_frame(self, tmp_path):
        """Absence is a state, not a crash (INTENT.md section 2)."""
        out = tmp_path / "screen.bmp"

        code = main(["--once", "--fixtures", str(SETS / "hostile"), "--out", str(out)])

        assert code == 0
        assert out.exists()

    def test_it_creates_the_output_directory(self, tmp_path):
        out = tmp_path / "frames" / "screen.bmp"

        assert main(["--once", "--out", str(out)]) == 0
        assert out.exists()

    def test_the_preview_sits_beside_the_composite(self):
        assert preview_path(Path("/var/dash/screen.bmp")) == Path("/var/dash/screen-preview.bmp")


@pytest.fixture(scope="module")
def day():
    """One simulated day from midnight, run once for the whole class."""
    return simulate(load_house(HOUSE))


class TestTheLoopObeysThePolicy:
    """A simulated day, asserted as invariants over what the loop did."""

    def test_the_day_actually_ran(self, day):
        _, clock, _, target = day

        assert clock.wall - MIDNIGHT >= timedelta(hours=23, minutes=59)
        assert target.fulls, "a whole day passed without a full refresh"
        assert target.partials, "a whole day passed without a partial refresh"

    def test_nothing_is_drawn_inside_the_vendor_floor(self, day):
        """The one rule with a hardware-damage story behind it."""
        _, _, _, target = day
        stamps = [entry[1] for entry in target.shown]

        gaps = [later - earlier for earlier, later in zip(stamps, stamps[1:])]

        assert gaps, "one refresh in a day proves nothing about the floor"
        assert min(gaps) >= FLOOR_SECONDS

    def test_no_full_cycle_spends_more_than_the_vendors_five_partials(self, day):
        _, _, _, target = day

        run_length = 0
        longest = 0
        for _, _, refresh, _ in target.shown:
            if refresh is Refresh.FULL:
                run_length = 0
            else:
                run_length += 1
                longest = max(longest, run_length)

        assert longest <= MAX_PARTIALS

    def test_the_panel_sleeps_through_the_night(self, day):
        """Except for the first frame, which has no previous image to hold."""
        _, _, _, target = day

        overnight = [
            when
            for when, _, _, _ in target.shown[1:]
            if when.time() >= DEFAULT_POLICY.quiet_start or when.time() < DEFAULT_POLICY.quiet_end
        ]

        assert overnight == []

    def test_the_first_frame_is_full_and_happens_at_midnight(self, day):
        """A process with no previous frame has no diff to write."""
        _, _, _, target = day
        when, _, refresh, _ = target.shown[0]

        assert refresh is Refresh.FULL
        assert when == MIDNIGHT

    def test_the_morning_window_tightens_the_cycle(self, day):
        """Section 4's 15 minutes, measured on the refreshes rather than read."""
        _, _, _, target = day
        morning = [
            mono
            for when, mono, refresh, _ in target.fulls
            if DEFAULT_POLICY.morning_start <= when.time() < DEFAULT_POLICY.morning_end
        ]

        gaps = [later - earlier for earlier, later in zip(morning, morning[1:])]

        assert len(morning) >= 9, "the 06:00-08:30 window should carry ten full cycles"
        assert max(gaps) <= DEFAULT_POLICY.morning_interval_seconds + TICK

    def test_the_daytime_cycle_is_the_half_hour(self, day):
        _, _, _, target = day
        daytime = [
            mono
            for when, mono, refresh, _ in target.fulls
            if DEFAULT_POLICY.morning_end <= when.time() < DEFAULT_POLICY.quiet_start
        ]

        gaps = [later - earlier for earlier, later in zip(daytime, daytime[1:])]

        assert max(gaps) <= DEFAULT_POLICY.full_interval_seconds + TICK

    def test_the_source_is_asked_only_when_something_is_being_drawn(self, day):
        """Deciding is arithmetic; fetching is a network round trip.

        2880 wakes, and the instance hears from us on the ~190 of them that
        put something on the glass.
        """
        _, _, source, target = day

        assert source.fetches == len(target.shown)
        assert source.fetches < 300

    def test_every_frame_carries_the_regions_it_changed(self, day):
        _, _, _, target = day

        assert all(items for _, _, _, items in target.shown)


class TestWhenTheSourceFails:
    """INTENT.md section 2: the last good frame is always better than no frame."""

    def test_the_wall_keeps_the_last_good_frame(self, config):
        code, _, source, target = simulate(config, ticks=400, start=MID_MORNING, fail_after=1)

        assert source.fetches > 1, "the loop stopped asking after the first failure"
        assert len(target.shown) > 1, "the screen went dark when the instance did"
        assert code == 0

    def test_the_stale_frame_is_the_same_frame(self, config):
        """Same draw list, same timestamp in the header - the frame ages visibly.

        Re-rendering the old snapshot with the current time would put a fresh
        clock on stale readings, which is the one lie this screen must not tell
        at a glance.
        """
        _, _, _, target = simulate(config, ticks=400, start=MID_MORNING, fail_after=1)

        first = target.shown[0][3]
        assert all(items == first for _, _, _, items in target.shown)

    def test_a_source_that_never_answers_draws_nothing_and_does_not_crash(self, config):
        source = DeadSource()
        code, _, _, target = simulate(config, ticks=20, source=source)

        assert target.shown == []
        assert source.fetches > 0
        assert code == 1

    def test_a_failing_target_does_not_advance_the_refresh_state(self, config):
        """A refresh that raised halfway through did not happen.

        If the loop recorded it anyway, a panel failing every cycle would burn
        its partial budget and its keep-alive on frames nobody ever saw.
        """
        clock = FakeClock()
        source = CountingSource(FixtureSource(config, FIXTURES))
        target = RecordingTarget(clock, fail=True)

        code = run(
            source,
            target,
            ticks=40,
            tick_seconds=TICK,
            now=clock.now,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        assert code == 1
        assert target.shown == []
        # Still trying, and still trying it as the first frame.
        assert source.fetches > 1

    def test_a_restored_refresh_state_is_honoured(self, config):
        """The seam PLAN.md M8.4 hangs a persisted timestamp on.

        A process that restarts inside the floor must not refresh because it is
        new; the state it was handed says the glass was written 10 seconds ago.
        """
        state = RefreshState(
            last_refresh_monotonic=0.0,
            last_full_monotonic=0.0,
            last_full_at=MIDNIGHT,
            partials_since_full=0,
        )
        clock = FakeClock(MIDNIGHT)
        target = RecordingTarget(clock)

        run(
            CountingSource(FixtureSource(config, FIXTURES)),
            target,
            state=state,
            ticks=5,
            tick_seconds=TICK,
            now=clock.now,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        assert target.shown == [], "a restart refreshed inside the 180 s floor"


class TestTheDirtySet:
    """The placeholder PLAN.md M9 replaces with a real draw-list diff."""

    def test_an_empty_frame_is_dirty_in_no_region(self):
        assert Frame().dirty.any is False

    def test_a_drawn_frame_reports_its_regions_by_update_class(self, config):
        from view.screen import screen

        items = screen(FixtureSource(config, FIXTURES).fetch())
        dirty = Frame(None, items).dirty

        assert dirty.partial == {i.region for i in items if i.update is UpdateClass.PARTIAL}
        assert dirty.full == {i.region for i in items if i.update is UpdateClass.FULL}
        assert not (dirty.partial & dirty.full), "a region cannot be both classes"

    def test_partial_refreshes_carry_only_partial_eligible_regions(self, config):
        """The thing that would put red on a plane that has no red."""
        from view.screen import screen

        items = screen(FixtureSource(config, FIXTURES).fetch())
        full_only = {i.region for i in items if i.update is UpdateClass.FULL}

        assert Frame(None, items).dirty.partial.isdisjoint(full_only)


class TestReadingTheEnvironment:
    def test_it_reads_a_plain_file(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("HASS_URL=http://ha.local:8123\nHASS_TOKEN=abc\n", encoding="utf-8")

        assert read_env_file(path) == {
            "HASS_URL": "http://ha.local:8123",
            "HASS_TOKEN": "abc",
        }

    def test_it_survives_the_shapes_a_hand_edited_file_takes(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text(
            "# the instance\n"
            "\n"
            "export HASS_URL = http://ha.local:8123 \n"
            'HASS_TOKEN="ey.J0eXAi=="\n'
            "NOT_A_PAIR\n",
            encoding="utf-8",
        )

        values = read_env_file(path)

        assert values["HASS_URL"] == "http://ha.local:8123"
        assert values["HASS_TOKEN"] == "ey.J0eXAi==", "padding after the first = was eaten"
        assert "NOT_A_PAIR" not in values

    def test_a_missing_file_is_not_an_error(self, tmp_path):
        """A deployment may keep its credentials in the environment only."""
        assert read_env_file(tmp_path / "nothing-here") == {}

    def test_the_real_environment_wins_over_the_file(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("HASS_URL=http://from-the-file\n", encoding="utf-8")

        merged = settings(path, {"HASS_URL": "http://from-the-shell"})

        assert merged["HASS_URL"] == "http://from-the-shell"


class TestBuildingTheSource:
    def test_the_fixture_source_needs_no_credentials(self, config):
        source = build_source("fixture", config, FIXTURES, {})

        assert isinstance(source, FixtureSource)

    def test_the_live_source_says_which_credential_is_missing(self, config):
        with pytest.raises(ConfigurationError) as error:
            build_source("hass", config, FIXTURES, {"HASS_URL": "http://ha.local:8123"})

        assert "HASS_TOKEN" in str(error.value)
        assert "HASS_URL" not in str(error.value)

    def test_a_url_ending_in_api_is_refused_with_the_fix(self, config):
        """The device's carried-over value, which would produce /api/api/states.

        A 404 that reads like a broken instance rather than a broken setting is
        exactly the failure worth catching at startup (PLAN.md M8).
        """
        with pytest.raises(ConfigurationError) as error:
            build_source(
                "hass",
                config,
                FIXTURES,
                {"HASS_URL": "http://ha.local:8123/api", "HASS_TOKEN": "t"},
            )

        assert "http://ha.local:8123" in str(error.value)

    def test_a_good_url_builds_without_opening_a_socket(self, config):
        source = build_source(
            "hass", config, FIXTURES, {"HASS_URL": "http://ha.local:8123/", "HASS_TOKEN": "t"}
        )

        assert source.name == "hass:http://ha.local:8123"


class TestBuildingTheTarget:
    def test_bmp_is_the_development_target(self, tmp_path):
        target = build_target("bmp", tmp_path / "screen.bmp")

        assert isinstance(target, BMPTarget)
        assert target.name == "bmp:screen.bmp"

    def test_the_panel_target_says_which_milestone_builds_it(self, tmp_path):
        """Better an honest refusal than a stub that pretends to drive a panel."""
        with pytest.raises(ConfigurationError) as error:
            build_target("epd", tmp_path / "screen.bmp")

        assert "M8" in str(error.value)

    def test_asking_for_the_panel_exits_rather_than_raising(self, tmp_path):
        assert main(["--target", "epd", "--once", "--out", str(tmp_path / "s.bmp")]) == 2

    def test_a_bad_house_file_exits_rather_than_raising(self, tmp_path):
        bad = tmp_path / "house.yml"
        bad.write_text("rooms: not-a-list\n", encoding="utf-8")

        assert main(["--once", "--house", str(bad), "--out", str(tmp_path / "s.bmp")]) == 2


class TestNothingHereTouchesHardware:
    """Per AGENTS.md: GPIO and SPI do not exist in the container."""

    def test_the_composition_root_imports_no_pin_configuration(self):
        import ast

        tree = ast.parse((ROOT / "src" / "app.py").read_text(encoding="utf-8"))
        imported = {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        } | {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }

        assert imported & {"epdconfig", "epd7in5b_V2", "gpiozero", "spidev"} == set()
