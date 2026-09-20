"""Tests for the refresh contract.

The unit cases pin each rule of INTENT.md section 4 at its boundary. The
simulation at the bottom is the one that matters: two days of ticks against a
frozen clock, across a Danish DST changeover, asserting the vendor's limits as
invariants over everything that happened rather than over one decision.

Two clocks run through every test here, because the device has two and they
answer different questions (HARDWARE.md section 6). Where a test advances them
apart on purpose, that is the point of the test.
"""

from datetime import datetime, time, timedelta, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo

from refresh.policy import (
    DEFAULT_POLICY,
    FLOOR_SECONDS,
    MAX_PARTIALS,
    Decision,
    Dirty,
    Policy,
    Reason,
    Refresh,
    RefreshState,
    decide,
    policy_violations,
    record,
)

UTC = timezone.utc
CPH = ZoneInfo("Europe/Copenhagen")

#: A normal tick: the clock in the header has moved, a room has warmed by a
#: tenth of a degree. Both classes dirty, which is the common case.
DIRTY = Dirty(partial=frozenset({"header.updated"}), full=frozenset({"rooms.stue.value"}))

FULL_INTERVAL = DEFAULT_POLICY.full_interval_seconds
MORNING_INTERVAL = DEFAULT_POLICY.morning_interval_seconds
PARTIAL_INTERVAL = DEFAULT_POLICY.partial_interval_seconds


def at(hour, minute=0, day=21, month=9, year=2026):
    """A local wall time in Copenhagen. 2026-09-21 is an ordinary Monday."""
    return datetime(year, month, day, hour, minute, tzinfo=CPH)


def settled(monotonic=10_000.0, now=None, partials=0):
    """A state as if a full refresh had just happened at `monotonic`."""
    return RefreshState(
        last_refresh_monotonic=monotonic,
        last_full_monotonic=monotonic,
        last_full_at=now or at(12),
        partials_since_full=partials,
    )


class TestTheVendorFloor:
    """180 s between refreshes of any class, and it outranks everything.

    HARDWARE.md section 3 calls it a recommendation. This project treats it as
    hard, because it is the rule with a damaged panel behind it.
    """

    def test_nothing_happens_inside_the_floor(self):
        state = settled()

        decision = decide(at(12), 10_000.0 + FLOOR_SECONDS - 0.1, state, DIRTY)

        assert decision.refresh is Refresh.NONE
        assert decision.reason is Reason.FLOOR

    def test_the_floor_is_inclusive_at_its_edge(self):
        # Exactly 180 s later is allowed; the vendor asks for "at least 180s".
        state = RefreshState(
            last_refresh_monotonic=0.0,
            last_full_monotonic=0.0,
            last_full_at=at(12),
            partials_since_full=0,
        )

        inside = decide(at(12, 2), FLOOR_SECONDS - 1, state, DIRTY)
        edge = decide(at(12, 3), FLOOR_SECONDS, state, DIRTY)

        assert inside.reason is Reason.FLOOR
        assert edge.reason is not Reason.FLOOR

    def test_the_floor_outranks_the_keep_alive(self):
        """24 h overdue does not buy a refresh 10 seconds after the last one.

        The two limits are three orders of magnitude apart, so they can only
        collide after a restart that has just drawn a frame. The floor wins.
        """
        state = RefreshState(
            last_refresh_monotonic=100.0,
            last_full_monotonic=100.0,
            last_full_at=at(12) - timedelta(hours=48),
            partials_since_full=0,
        )

        decision = decide(at(12), 110.0, state, DIRTY)

        assert decision.reason is Reason.FLOOR

    def test_a_monotonic_reading_of_zero_is_a_reading(self):
        """`or` instead of an explicit None check would discard it silently."""
        state = RefreshState(
            last_refresh_monotonic=0.0,
            last_full_monotonic=0.0,
            last_full_at=at(12),
        )

        decision = decide(at(12), 60.0, state, DIRTY)

        assert decision.reason is Reason.FLOOR


class TestTheFirstFrame:
    """A process that has drawn nothing draws everything."""

    def test_fresh_state_is_a_full_refresh(self):
        decision = decide(at(12), 0.0)

        assert decision.refresh is Refresh.FULL
        assert decision.reason is Reason.FIRST_FRAME

    def test_the_first_frame_ignores_quiet_hours(self):
        # A blank screen is not a quiet screen. Starting at 03:00 draws.
        decision = decide(at(3), 0.0, RefreshState(), DIRTY)

        assert decision.refresh is Refresh.FULL
        assert decision.reason is Reason.FIRST_FRAME

    def test_a_restart_with_a_persisted_timestamp_still_draws_a_full_frame(self):
        """There is no previous buffer to refresh partially against.

        M8.4 persists `last_full_at` across restarts so the floor and the
        keep-alive survive a reboot. What it cannot persist is the frame on the
        glass, so the first refresh of a new process is always full.
        """
        state = RefreshState(last_full_at=at(11, 55))

        decision = decide(at(12), 0.0, state, DIRTY)

        assert decision.refresh is Refresh.FULL
        assert decision.reason is Reason.FIRST_FRAME

    def test_a_restart_loop_cannot_beat_the_floor(self):
        """The persisted timestamp is what holds it, so it must be respected.

        A crash-restart cycle re-enters with fresh monotonic state. If the app
        reconstructs `last_refresh_monotonic` from disk, the floor holds; the
        policy's job is only to honour it when it is there.
        """
        state = RefreshState(last_refresh_monotonic=0.0, last_full_at=at(11, 59))

        decision = decide(at(12), 30.0, state, DIRTY)

        assert decision.refresh is Refresh.NONE
        assert decision.reason is Reason.FLOOR


class TestTheFullCycle:
    """Every 30 minutes, tightened to 15 in the morning window."""

    def test_nothing_full_before_thirty_minutes(self):
        state = settled(0.0)

        decision = decide(at(12, 29), FULL_INTERVAL - 60, state, Dirty())

        assert decision.refresh is Refresh.NONE

    def test_a_full_refresh_at_thirty_minutes(self):
        state = settled(0.0)

        decision = decide(at(12, 30), FULL_INTERVAL, state, DIRTY)

        assert decision.refresh is Refresh.FULL
        assert decision.reason is Reason.CADENCE

    def test_the_morning_window_tightens_it_to_fifteen(self):
        state = settled(0.0, now=at(7))

        decision = decide(at(7, 15), MORNING_INTERVAL, state, DIRTY)

        assert decision.refresh is Refresh.FULL
        assert decision.reason is Reason.MORNING_CADENCE

    def test_the_same_fifteen_minutes_outside_the_window_is_not_enough(self):
        state = settled(0.0, now=at(13))

        decision = decide(at(13, 15), MORNING_INTERVAL, state, DIRTY)

        assert decision.refresh is not Refresh.FULL

    def test_the_morning_window_runs_from_six_to_half_past_eight(self):
        state = settled(0.0)
        monotonic = MORNING_INTERVAL

        # 06:00 is the first tightened tick; 08:30 is the first that is not.
        assert decide(at(5, 59), monotonic, state, DIRTY).reason is Reason.QUIET_HOURS
        assert decide(at(6, 0), monotonic, state, DIRTY).reason is Reason.MORNING_CADENCE
        assert decide(at(8, 29), monotonic, state, DIRTY).reason is Reason.MORNING_CADENCE
        assert decide(at(8, 30), monotonic, state, DIRTY).refresh is not Refresh.FULL

    def test_the_cycle_runs_on_time_and_not_on_news(self):
        """Red lags. Section 4 accepts this consequence explicitly.

        A room crossing into alert marks the frame full-dirty and waits: the
        same tick decides identically whether or not anything changed.
        """
        state = settled(0.0)

        clean = decide(at(12, 20), 20 * 60, state, Dirty())
        alerting = decide(at(12, 20), 20 * 60, state, Dirty(full=frozenset({"rooms.bad.value"})))

        assert clean.refresh is Refresh.NONE
        assert alerting.refresh is Refresh.NONE

    def test_a_full_refresh_reports_everything_dirty_as_news(self):
        state = settled(0.0)

        decision = decide(at(12, 30), FULL_INTERVAL, state, DIRTY)

        assert decision.regions == frozenset({"header.updated", "rooms.stue.value"})


class TestQuietHours:
    """No refresh at all overnight. The panel ages instead of informing nobody."""

    def test_the_middle_of_the_night_refreshes_nothing(self):
        state = settled(0.0, now=at(21, 55))

        decision = decide(at(3), 6 * 3600, state, DIRTY)

        assert decision.refresh is Refresh.NONE
        assert decision.reason is Reason.QUIET_HOURS

    def test_quiet_hours_start_at_twenty_two(self):
        state = settled(0.0)
        monotonic = FULL_INTERVAL

        assert decide(at(21, 59), monotonic, state, DIRTY).refresh is Refresh.FULL
        assert decide(at(22, 0), monotonic, state, DIRTY).refresh is Refresh.NONE

    def test_quiet_hours_and_the_morning_window_tile_exactly(self):
        """06:00 belongs to the morning, not to the night.

        The two windows are half-open and share an edge, so there is no minute
        that is both and no minute that is neither.
        """
        state = settled(0.0)
        monotonic = FULL_INTERVAL

        assert decide(at(5, 59), monotonic, state, DIRTY).reason is Reason.QUIET_HOURS
        assert decide(at(6, 0), monotonic, state, DIRTY).reason is Reason.MORNING_CADENCE

    def test_quiet_hours_stop_partials_too(self):
        state = settled(0.0, now=at(21, 55), partials=0)

        decision = decide(at(23), PARTIAL_INTERVAL * 2, state, DIRTY)

        assert decision.refresh is Refresh.NONE
        assert decision.reason is Reason.QUIET_HOURS


class TestTheKeepAlive:
    """At least one refresh every 24 h, whatever else the policy says.

    Measured on wall time on purpose: it is the one rule that has to survive a
    reboot, and a monotonic clock restarts at zero (HARDWARE.md section 6).
    """

    def test_twenty_four_hours_overrides_quiet_hours(self):
        state = RefreshState(
            last_refresh_monotonic=0.0,
            last_full_monotonic=0.0,
            last_full_at=at(3) - timedelta(hours=24),
        )

        decision = decide(at(3), 24 * 3600, state, DIRTY)

        assert decision.refresh is Refresh.FULL
        assert decision.reason is Reason.KEEP_ALIVE

    def test_it_fires_exactly_at_twenty_four_hours(self):
        just_under = RefreshState(
            last_refresh_monotonic=0.0,
            last_full_monotonic=0.0,
            last_full_at=at(3) - timedelta(hours=24) + timedelta(minutes=1),
        )
        state = RefreshState(
            last_refresh_monotonic=0.0,
            last_full_monotonic=0.0,
            last_full_at=at(3) - timedelta(hours=24),
        )

        assert decide(at(3), 24 * 3600, just_under, DIRTY).reason is Reason.QUIET_HOURS
        assert decide(at(3), 24 * 3600, state, DIRTY).reason is Reason.KEEP_ALIVE

    def test_a_wall_clock_landing_from_ntp_fires_it_once_and_not_a_storm(self):
        """The cold-boot case: `fake-hwclock` is days out until NTP lands.

        The jump makes the panel look 48 h stale, which earns one full refresh.
        Recording it stamps the corrected wall time, so the next tick is back
        on the ordinary cadence.
        """
        state = settled(0.0, now=at(12))
        landed = at(12) + timedelta(days=2)

        first = decide(landed, 600.0, state, DIRTY)
        state = record(state, first, landed, 600.0)
        second = decide(landed + timedelta(minutes=5), 900.0, state, DIRTY)

        assert first.reason is Reason.KEEP_ALIVE
        assert second.refresh is not Refresh.FULL

    def test_a_backwards_wall_clock_jump_does_not_stall_the_panel(self):
        """The rule that makes the two-clock split worth its complexity.

        Wall time going backwards makes the keep-alive un-fireable - the panel
        looks freshly refreshed for as long as the jump lasted. The cadence
        runs on the monotonic clock, so it carries on regardless.
        """
        state = settled(0.0, now=at(12) + timedelta(days=1))

        decision = decide(at(12), FULL_INTERVAL, state, DIRTY)

        assert decision.refresh is Refresh.FULL
        assert decision.reason is Reason.CADENCE

    def test_a_backwards_wall_clock_jump_does_not_defeat_the_floor(self):
        """And the floor, which is the one that damages hardware, is untouched."""
        state = settled(0.0, now=at(12) + timedelta(days=1))

        decision = decide(at(12), 60.0, state, DIRTY)

        assert decision.reason is Reason.FLOOR

    def test_quiet_hours_cannot_starve_it_however_long_they_are(self):
        """Which is why no policy check guards against that: the order does.

        The keep-alive is decided before quiet hours, so a night stretched to
        23 hours still gets interrupted by one full refresh rather than letting
        the panel drift past the burn-in limit.
        """
        nocturnal = Policy(quiet_start=time(7, 0), quiet_end=time(6, 0))
        state = RefreshState(
            last_refresh_monotonic=0.0,
            last_full_monotonic=0.0,
            last_full_at=at(3) - timedelta(hours=24),
        )

        decision = decide(at(3), 24 * 3600, state, DIRTY, nocturnal)

        assert decision.reason is Reason.KEEP_ALIVE


class TestPartialRefresh:
    """Every 5 minutes between full cycles, for red-free regions only."""

    def test_a_partial_when_something_partial_eligible_changed(self):
        state = settled(0.0)

        decision = decide(at(12, 5), PARTIAL_INTERVAL, state, DIRTY)

        assert decision.refresh is Refresh.PARTIAL
        assert decision.reason is Reason.PARTIAL_DUE
        assert decision.regions == frozenset({"header.updated"})

    def test_nothing_when_only_full_only_regions_changed(self):
        """A partial refresh cannot carry a room value, so there is nothing to do."""
        state = settled(0.0)

        decision = decide(at(12, 5), PARTIAL_INTERVAL, state, Dirty(full=frozenset({"rooms.stue"})))

        assert decision.refresh is Refresh.NONE
        assert decision.reason is Reason.NOTHING_CHANGED

    def test_nothing_when_nothing_changed(self):
        state = settled(0.0)

        decision = decide(at(12, 5), PARTIAL_INTERVAL, state, Dirty())

        assert decision.reason is Reason.NOTHING_CHANGED

    def test_waiting_before_the_interval_is_up(self):
        state = settled(0.0)

        decision = decide(at(12, 4), PARTIAL_INTERVAL - 60, state, DIRTY)

        assert decision.refresh is Refresh.NONE
        assert decision.reason is Reason.WAITING

    def test_the_interval_runs_from_any_refresh_not_just_the_last_partial(self):
        # Three minutes after a full is past the floor but not past the cycle.
        state = settled(0.0)

        decision = decide(at(12, 3), 180.0, state, DIRTY)

        assert decision.reason is Reason.WAITING

    def test_the_budget_stops_at_the_vendors_five(self):
        state = RefreshState(
            last_refresh_monotonic=1400.0,
            last_full_monotonic=0.0,
            last_full_at=at(12),
            partials_since_full=MAX_PARTIALS,
        )

        decision = decide(at(12, 29), 1750.0, state, DIRTY)

        assert decision.refresh is Refresh.NONE
        assert decision.reason is Reason.PARTIAL_BUDGET

    def test_the_budget_resets_on_a_full_refresh(self):
        state = RefreshState(
            last_refresh_monotonic=1400.0,
            last_full_monotonic=0.0,
            last_full_at=at(12),
            partials_since_full=MAX_PARTIALS,
        )

        state = record(state, Decision(Refresh.FULL, Reason.CADENCE), at(12, 30), FULL_INTERVAL)
        decision = decide(at(12, 35), FULL_INTERVAL + PARTIAL_INTERVAL, state, DIRTY)

        assert state.partials_since_full == 0
        assert decision.refresh is Refresh.PARTIAL


class TestRecord:
    """State only advances on a refresh that actually happened."""

    def test_a_full_refresh_stamps_both_clocks_and_clears_the_budget(self):
        state = RefreshState(partials_since_full=3)

        state = record(state, Decision(Refresh.FULL, Reason.CADENCE), at(12), 500.0)

        assert state.last_refresh_monotonic == 500.0
        assert state.last_full_monotonic == 500.0
        assert state.last_full_at == at(12)
        assert state.partials_since_full == 0

    def test_a_partial_spends_budget_and_leaves_the_full_clocks_alone(self):
        state = settled(100.0)

        state = record(state, Decision(Refresh.PARTIAL, Reason.PARTIAL_DUE), at(12, 5), 400.0)

        assert state.last_refresh_monotonic == 400.0
        assert state.last_full_monotonic == 100.0
        assert state.last_full_at == at(12)
        assert state.partials_since_full == 1

    def test_a_decision_to_do_nothing_changes_nothing(self):
        state = settled(100.0, partials=2)

        assert record(state, Decision(Refresh.NONE, Reason.WAITING), at(12), 999.0) == state


class TestThePolicyNumbers:
    """Section 4's arithmetic, restated so a changed number cannot break it quietly."""

    def test_the_shipped_policy_is_consistent(self):
        assert policy_violations(DEFAULT_POLICY) == ()

    def test_exactly_five_partials_fit_in_a_full_cycle(self):
        """Section 4's central claim: the vendor limit and the cadence coincide.

        30 minutes at one partial every 5 leaves five partials and then the
        full refresh the vendor wanted anyway, rather than a sixth.
        """
        partials = (
            DEFAULT_POLICY.full_interval_seconds / DEFAULT_POLICY.partial_interval_seconds - 1
        )

        assert partials == MAX_PARTIALS
        assert DEFAULT_POLICY.max_partials == MAX_PARTIALS

    def test_the_partial_cycle_clears_the_floor(self):
        assert DEFAULT_POLICY.partial_interval_seconds > FLOOR_SECONDS

    def test_a_policy_scheduling_inside_the_floor_is_reported(self):
        found = policy_violations(Policy(partial_interval_seconds=120))

        assert any("inside the 180s floor" in line for line in found)

    def test_a_floor_under_the_vendors_is_reported(self):
        found = policy_violations(Policy(floor_seconds=60))

        assert any("under the vendor's 180s" in line for line in found)

    def test_a_morning_window_that_loosens_the_cycle_is_reported(self):
        found = policy_violations(Policy(morning_interval_seconds=60 * 60))

        assert any("loosens" in line for line in found)

    def test_a_sixth_partial_per_cycle_is_reported(self):
        found = policy_violations(Policy(max_partials=6))

        assert any("exceeds the vendor's 5" in line for line in found)

    def test_a_keep_alive_past_the_burn_in_limit_is_reported(self):
        found = policy_violations(Policy(keep_alive=timedelta(hours=30)))

        assert any("burn-in" in line for line in found)

    def test_a_morning_window_that_wraps_midnight_is_reported(self):
        found = policy_violations(Policy(morning_start=time(8, 30), morning_end=time(6, 0)))

        assert any("wraps midnight" in line for line in found)

    def test_a_morning_window_buried_in_quiet_hours_is_reported(self):
        found = policy_violations(Policy(quiet_start=time(22, 0), quiet_end=time(9, 0)))

        assert any("never run" in line for line in found)


class Event(NamedTuple):
    """One refresh that happened, with both clocks as they read at the time."""

    now: datetime
    monotonic: float
    decision: Decision


class Simulation:
    """A loop with no panel, no source and no renderer: ticks, and a log.

    The wall clock is advanced through UTC rather than by adding a timedelta to
    a local datetime. Aware arithmetic in Python is wall-clock arithmetic - it
    keeps the same tzinfo and does not renormalise - so adding an hour across a
    DST boundary the naive way would skip the changeover the test exists to
    exercise.
    """

    def __init__(self, start, policy=DEFAULT_POLICY, dirty=DIRTY):
        self.now = start
        self.monotonic = 0.0
        self.state = RefreshState()
        self.policy = policy
        self.dirty = dirty
        self.events: list[Event] = []

    def run(self, hours, tick=60):
        for _ in range(int(hours * 3600 // tick)):
            decision = decide(self.now, self.monotonic, self.state, self.dirty, self.policy)
            if decision.refreshes:
                self.events.append(Event(self.now, self.monotonic, decision))
                self.state = record(self.state, decision, self.now, self.monotonic)
            self.now = (self.now.astimezone(UTC) + timedelta(seconds=tick)).astimezone(CPH)
            self.monotonic += tick
        return self

    def of(self, refresh):
        return [event for event in self.events if event.decision.refresh is refresh]


def is_quiet(moment, policy):
    """The half-open, midnight-wrapping window, restated rather than imported.

    A test that asked the module whether it was quiet would agree with the
    module by construction. This is the same rule written independently.
    """
    start, end = policy.quiet_start, policy.quiet_end
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end


def assert_contract_held(sim):
    """The vendor's limits, asserted over everything that happened.

    These are the four rules that carry a hardware consequence, checked as
    properties of the whole run rather than of any one decision - which is the
    only way a scheduling bug that needs three ticks to show up gets caught.
    """
    events = sim.events

    for earlier, later in zip(events, events[1:]):
        gap = later.monotonic - earlier.monotonic
        assert gap >= FLOOR_SECONDS, f"{gap:.0f}s apart at {later.now}, inside the floor"

    spent = 0
    for event in events:
        if event.decision.refresh is Refresh.FULL:
            spent = 0
        else:
            spent += 1
            assert spent <= MAX_PARTIALS, f"{spent} partials without a full, at {event.now}"

    fulls = sim.of(Refresh.FULL)
    for earlier, later in zip(fulls, fulls[1:]):
        gap = later.now - earlier.now
        assert gap <= timedelta(hours=24), f"{gap} between full refreshes, past the burn-in limit"

    allowed = {Reason.KEEP_ALIVE, Reason.FIRST_FRAME}
    for event in events:
        if is_quiet(event.now.time(), sim.policy):
            assert event.decision.reason in allowed, f"{event.decision.reason} at {event.now}"


class TestFortyEightHours:
    """The contract over two simulated days, one minute at a time."""

    def test_the_vendor_limits_hold_across_two_days(self):
        sim = Simulation(at(0)).run(hours=48)

        assert_contract_held(sim)

    def test_the_day_has_the_shape_section_four_describes(self):
        sim = Simulation(at(0)).run(hours=24)
        fulls = sim.of(Refresh.FULL)
        hours = sorted({event.now.hour for event in fulls})

        # First frame at 00:00, then nothing until quiet hours end at 06:00.
        assert fulls[0].decision.reason is Reason.FIRST_FRAME
        assert fulls[0].now == at(0)
        assert fulls[1].now == at(6)
        assert hours == [0] + list(range(6, 22))

    def test_the_morning_window_doubles_the_cadence(self):
        sim = Simulation(at(0)).run(hours=24)
        morning = [e for e in sim.of(Refresh.FULL) if e.decision.reason is Reason.MORNING_CADENCE]
        ordinary = [e for e in sim.of(Refresh.FULL) if e.decision.reason is Reason.CADENCE]

        # 06:00 to 08:15 inclusive at 15-minute spacing.
        assert [(e.now.hour, e.now.minute) for e in morning[:3]] == [(6, 0), (6, 15), (6, 30)]
        assert len(morning) == 10
        assert all(
            (later.now - earlier.now) == timedelta(minutes=30)
            for earlier, later in zip(ordinary, ordinary[1:])
        )

    def test_exactly_five_partials_ride_each_ordinary_full_cycle(self):
        sim = Simulation(at(12)).run(hours=12)
        between = []
        spent = 0
        for event in sim.events:
            if event.decision.refresh is Refresh.FULL:
                between.append(spent)
                spent = 0
            else:
                spent += 1

        # The first entry is the count before the first frame, which is zero.
        assert set(between[2:]) == {MAX_PARTIALS}

    def test_the_night_is_silent(self):
        sim = Simulation(at(12)).run(hours=24)
        overnight = [e for e in sim.events if time(22, 0) <= e.now.time() or e.now.time() < time(6)]

        assert overnight == []

    def test_red_never_accelerates_a_cycle(self):
        """Two runs, identical but for a permanently alerting room.

        Section 4's accepted consequence, asserted over two days rather than
        argued: the timing of every refresh is the same whether or not a
        full-only region is screaming.
        """
        calm = Simulation(at(0), dirty=Dirty(partial=frozenset({"header.updated"}))).run(hours=48)
        alarmed = Simulation(at(0), dirty=DIRTY).run(hours=48)

        assert [e.monotonic for e in calm.events] == [e.monotonic for e in alarmed.events]

    def test_a_screen_with_nothing_to_say_still_gets_its_full_cycles(self):
        """Partials stop; the full cadence does not. The panel needs it anyway."""
        sim = Simulation(at(0), dirty=Dirty()).run(hours=48)

        assert sim.of(Refresh.PARTIAL) == []
        assert len(sim.of(Refresh.FULL)) > 40
        assert_contract_held(sim)

    def test_an_almost_entirely_quiet_day_still_beats_the_burn_in_limit(self):
        """Quiet hours stretched to 23 of the 24, as the worst case allowed.

        One waking hour a day is enough, because it overlaps the morning
        window: the burn-in gap comes out at 23h15m and the keep-alive never
        has to intervene at all.
        """
        nocturnal = Policy(quiet_start=time(7, 0), quiet_end=time(6, 0))
        sim = Simulation(at(0), policy=nocturnal).run(hours=48)
        fulls = sim.of(Refresh.FULL)

        assert_contract_held(sim)
        assert {(e.now.hour, e.now.minute) for e in fulls[1:]} == {
            (6, 0),
            (6, 15),
            (6, 30),
            (6, 45),
        }
        assert all(e.decision.reason is not Reason.KEEP_ALIVE for e in fulls)


class TestAcrossADSTChangeover:
    """Danish clocks go back on 2026-10-25, making that day 25 hours long.

    The split between the two clocks is what makes this uneventful: the
    cadences never see the repeated hour because they are counted in monotonic
    seconds, and the windows see it correctly because they are read off local
    wall time. The test exists to prove the uneventfulness rather than assume
    it.
    """

    def test_the_contract_holds_through_the_repeated_hour(self):
        sim = Simulation(at(12, day=24, month=10)).run(hours=48)

        assert_contract_held(sim)

    def test_the_repeated_hour_is_quiet_both_times(self):
        # 02:00-03:00 local happens twice and falls inside quiet hours twice.
        sim = Simulation(at(12, day=24, month=10)).run(hours=48)
        repeated = [e for e in sim.events if e.now.date().day == 25 and e.now.hour == 2]

        assert repeated == []

    def test_the_extra_hour_is_an_hour_of_monotonic_time_the_cadence_counts(self):
        """25 hours of clock, 25 hours of ticks, one ordinary set of refreshes.

        A cadence measured on local wall time would have refreshed through the
        repeated hour twice or not at all; measured on the steady clock it
        simply spends an extra hour in quiet hours.
        """
        sim = Simulation(at(0, day=25, month=10)).run(hours=25)

        assert sim.now.date().day == 26
        assert sim.now.hour == 0
        assert sim.monotonic == 25 * 3600
        assert_contract_held(sim)

    def test_quiet_hours_still_end_once_at_six(self):
        sim = Simulation(at(0, day=25, month=10)).run(hours=25)
        first = sim.of(Refresh.FULL)[1]

        assert (first.now.hour, first.now.minute) == (6, 0)
        assert first.decision.reason is Reason.MORNING_CADENCE
