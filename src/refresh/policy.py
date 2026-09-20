"""The refresh contract of INTENT.md section 4, as one pure decision.

`decide()` takes the clocks, what happened last time, and what changed, and
returns *none*, *partial* or *full* with the reason it chose. It performs no
I/O, imports nothing from `render/`, and does not know a panel exists - which
is what lets a simulated 48 hours run in milliseconds and what keeps the
vendor's hard limits in a place where they can be asserted rather than hoped
for.

**Two clocks, because the target has two and they answer different questions.**
The board has no RTC (HARDWARE.md section 6): after a cold boot the system time
is whatever `fake-hwclock` last wrote, and it jumps - possibly by days - when
NTP lands. So:

*Durations are measured on a monotonic clock.* The 180 s floor, the 30-minute
full cycle and the 5-minute partial cycle all ask "how long has the glass been
standing", and a wall-clock jump must not answer that question. A backwards
jump would otherwise permit a refresh inside the vendor floor; a forwards jump
would stall the panel.

*Wall time answers "what time is it".* Quiet hours and the morning window are
times of day, and the 24 h keep-alive is measured against wall time on purpose:
it is the one rule that has to survive a reboot, and a monotonic clock restarts
at zero while a persisted wall timestamp does not (HARDWARE.md section 6 says
exactly this).

**Red lags on purpose.** A dirty full-only region - a room that has just
crossed into alert - does not accelerate anything. Section 4: "A value crossing
into alert state marks the frame full-dirty and waits." It is reported in the
decision so the log can say what the cycle carried, and that is all it does.
The alternative is flashing the hallway wall for 26 seconds every time a
bathroom warms by a tenth of a degree.

**The numbers live in `Policy` and are checked, not trusted.**
`policy_violations()` holds the arithmetic that section 4 states in prose - that
nothing may schedule inside the floor, that the morning window tightens the
cycle rather than loosening it, that the partial budget is the vendor's five.

What this module does *not* do is decide which regions are dirty. That is a
diff of two draw lists, it belongs in `render/` (INTENT.md section 6), and M9
builds it. Until then a caller supplies `Dirty` itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum

#: The vendor floor between refreshes of any class, in seconds. HARDWARE.md
#: section 3 calls it a recommendation; this project treats it as hard.
FLOOR_SECONDS = 180.0

#: The vendor's limit on consecutive partial refreshes before the image
#: degrades and a full one is required.
MAX_PARTIALS = 5


class Refresh(Enum):
    """What to do this tick.

    Deliberately not `view.drawlist.UpdateClass`, though two of the three names
    match. That enum answers "what does this item need to reach the glass";
    this one answers "what is the loop about to do", and doing nothing is the
    most common answer by a wide margin.
    """

    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"


class Reason(Enum):
    """Why. Every decision carries one, because M7 logs what was refreshed and
    why, and "why not" is the answer that is hard to reconstruct afterwards."""

    FLOOR = "floor"
    FIRST_FRAME = "first_frame"
    KEEP_ALIVE = "keep_alive"
    QUIET_HOURS = "quiet_hours"
    CADENCE = "cadence"
    MORNING_CADENCE = "morning_cadence"
    PARTIAL_DUE = "partial_due"
    PARTIAL_BUDGET = "partial_budget"
    NOTHING_CHANGED = "nothing_changed"
    WAITING = "waiting"


@dataclass(frozen=True)
class Policy:
    """Section 4's cadence, as numbers in one place.

    The defaults are the ones the contract argues for: 30 minutes between full
    refreshes, 15 during the morning window when the screen is actually being
    read, a partial every 5 minutes between them - which is both comfortably
    above the 180 s floor and exactly the vendor's 5 partials per full cycle.
    The two rules coincide rather than conflict, which is why these numbers and
    not others.

    Quiet hours are the one number section 4 describes without fixing: it says
    "overnight" and leaves it there. 22:00-06:00 is the reading taken here - it
    ends exactly where the morning window begins, so the two tile with no gap,
    and it errs towards the panel ageing less rather than towards informing a
    dark hallway.
    """

    floor_seconds: float = FLOOR_SECONDS
    full_interval_seconds: float = 30 * 60
    morning_interval_seconds: float = 15 * 60
    partial_interval_seconds: float = 5 * 60
    max_partials: int = MAX_PARTIALS
    morning_start: time = time(6, 0)
    morning_end: time = time(8, 30)
    quiet_start: time = time(22, 0)
    quiet_end: time = time(6, 0)
    keep_alive: timedelta = timedelta(hours=24)


DEFAULT_POLICY = Policy()

#: The same cadence, for a target that has no partial path at all.
#:
#: Zero budget rather than a longer partial interval, because the honest
#: statement is "this one cannot do partials", not "it does them rarely". The
#: full cycle is untouched: 30 minutes, 15 in the morning, and quiet hours
#: unchanged. PLAN.md M8 pairs it with the panel, which can write red only
#: inside a full refresh (HARDWARE.md section 4), and M9 is where that may
#: stop being true.
FULL_ONLY_POLICY = Policy(max_partials=0)


@dataclass(frozen=True)
class Dirty:
    """Which regions changed since the frame on the glass, by update class.

    Two sets rather than one, because the classes are not interchangeable:
    `partial` is what a partial refresh could carry, and `full` is what has to
    wait for the 26-second cycle whatever else happens. Region names rather
    than booleans, because M9 turns them into 8-aligned windows and the log
    line reads better naming them.
    """

    partial: frozenset[str] = frozenset()
    full: frozenset[str] = frozenset()

    @property
    def any(self) -> bool:
        return bool(self.partial or self.full)


NOTHING_DIRTY = Dirty()


@dataclass(frozen=True)
class RefreshState:
    """What happened last time, in the clock each rule is entitled to.

    `last_refresh_monotonic` and `last_full_monotonic` are readings from a
    steady clock - `time.monotonic()` on the device - and are named for it
    because a field holding seconds-since-boot that reads like a timestamp is
    the kind of thing that gets silently compared against wall time once and
    then defeats the floor for the life of the project.

    `last_full_at` is wall time and is the field M8.4 persists to disk. It is
    the only one that survives a reboot, which is exactly why the 24 h
    keep-alive is the rule that uses it.

    Fresh state - every field at its default - means "this process has never
    drawn a frame", which is a full refresh and not a partial one: a partial
    refresh writes changed regions onto whatever the panel is already holding,
    and a process with no previous frame has no diff to write.
    """

    last_refresh_monotonic: float | None = None
    last_full_monotonic: float | None = None
    last_full_at: datetime | None = None
    partials_since_full: int = 0


@dataclass(frozen=True)
class Decision:
    """What to do, why, and which changed regions it carries.

    `regions` is the dirty set this refresh puts on the glass: the partial
    regions for a partial refresh, everything dirty for a full one - which
    repaints the whole frame regardless, but only these regions are news.
    """

    refresh: Refresh
    reason: Reason
    regions: frozenset[str] = frozenset()

    @property
    def refreshes(self) -> bool:
        return self.refresh is not Refresh.NONE


def decide(
    now: datetime,
    monotonic: float,
    state: RefreshState = RefreshState(),
    dirty: Dirty = NOTHING_DIRTY,
    policy: Policy = DEFAULT_POLICY,
) -> Decision:
    """The whole contract, in the order the rules override one another.

    `now` is local wall time and should be timezone-aware in the household's
    zone; `now.time()` is what quiet hours and the morning window are read
    from, and an aware `now` is required for the keep-alive to compare against
    a stored `last_full_at`.

    `monotonic` is any steady, forward-only seconds reading. Its origin is
    irrelevant - only differences are ever taken - so tests pass a counter.

    The order is the argument:

    1. **The floor wins over everything**, including the keep-alive and the
       first frame. It is the one rule with a hardware-damage story behind it,
       and 180 s never competes with 24 h.
    2. **A process that has drawn nothing draws a full frame**, even at 03:00.
       A blank screen is not a quiet screen, and there is no previous buffer to
       refresh partially against.
    3. **The keep-alive overrides quiet hours**, because section 4 says so and
       burn-in does not care what time it is.
    4. **Quiet hours stop everything else.** E-paper holds its image; the panel
       ages instead of informing nobody.
    5. **The full cycle runs on time, not on news.** Red lags by design.
    6. **A partial needs budget, a due time, and something to say.**
    """
    if state.last_refresh_monotonic is not None:
        if monotonic - state.last_refresh_monotonic < policy.floor_seconds:
            return Decision(Refresh.NONE, Reason.FLOOR)

    if state.last_full_monotonic is None:
        return Decision(Refresh.FULL, Reason.FIRST_FRAME, _carried(dirty))

    if _keep_alive_due(now, state, policy):
        return Decision(Refresh.FULL, Reason.KEEP_ALIVE, _carried(dirty))

    if _within(now.time(), policy.quiet_start, policy.quiet_end):
        return Decision(Refresh.NONE, Reason.QUIET_HOURS)

    morning = _within(now.time(), policy.morning_start, policy.morning_end)
    interval = policy.morning_interval_seconds if morning else policy.full_interval_seconds
    if monotonic - state.last_full_monotonic >= interval:
        reason = Reason.MORNING_CADENCE if morning else Reason.CADENCE
        return Decision(Refresh.FULL, reason, _carried(dirty))

    # Explicitly against None, not truthiness: a monotonic clock is perfectly
    # entitled to read 0.0, and `or` would quietly discard that reading.
    last_refresh = state.last_refresh_monotonic
    if last_refresh is None:
        last_refresh = state.last_full_monotonic
    if monotonic - last_refresh < policy.partial_interval_seconds:
        return Decision(Refresh.NONE, Reason.WAITING)

    if state.partials_since_full >= policy.max_partials:
        # Refusing is what the vendor rule asks for: the image degrades from
        # doing a sixth partial, not from sitting on the fifth. The next full
        # is at most one partial interval away, by construction.
        return Decision(Refresh.NONE, Reason.PARTIAL_BUDGET)

    if not dirty.partial:
        return Decision(Refresh.NONE, Reason.NOTHING_CHANGED)

    return Decision(Refresh.PARTIAL, Reason.PARTIAL_DUE, frozenset(dirty.partial))


def record(
    state: RefreshState,
    decision: Decision,
    now: datetime,
    monotonic: float,
) -> RefreshState:
    """The state after a refresh that actually happened.

    Called once the panel has been written and put back to sleep, never on the
    strength of the decision alone - a refresh that raised halfway through did
    not reset the partial budget, and pretending otherwise would let a failing
    cycle run the count past the vendor's five.
    """
    if decision.refresh is Refresh.FULL:
        return RefreshState(
            last_refresh_monotonic=monotonic,
            last_full_monotonic=monotonic,
            last_full_at=now,
            partials_since_full=0,
        )

    if decision.refresh is Refresh.PARTIAL:
        return RefreshState(
            last_refresh_monotonic=monotonic,
            last_full_monotonic=state.last_full_monotonic,
            last_full_at=state.last_full_at,
            partials_since_full=state.partials_since_full + 1,
        )

    return state


def policy_violations(policy: Policy = DEFAULT_POLICY) -> tuple[str, ...]:
    """Everything wrong with a set of numbers, as readable lines.

    Returns rather than raises, in the same spirit as
    `view.drawlist.violations()`: a test asserts on the whole set at once, and
    the default policy is expected to produce none. These are section 4's
    claims restated as arithmetic, so that changing one number cannot quietly
    break the rule that made it defensible.
    """
    found: list[str] = []

    if policy.floor_seconds < FLOOR_SECONDS:
        found.append(
            f"floor {policy.floor_seconds:.0f}s is under the vendor's {FLOOR_SECONDS:.0f}s"
        )

    for name, seconds in (
        ("partial interval", policy.partial_interval_seconds),
        ("full interval", policy.full_interval_seconds),
        ("morning interval", policy.morning_interval_seconds),
    ):
        if seconds < policy.floor_seconds:
            found.append(
                f"{name} {seconds:.0f}s schedules inside the {policy.floor_seconds:.0f}s floor"
            )

    if policy.morning_interval_seconds > policy.full_interval_seconds:
        found.append("the morning window loosens the full cycle instead of tightening it")

    if policy.max_partials > MAX_PARTIALS:
        found.append(f"{policy.max_partials} partials per full exceeds the vendor's {MAX_PARTIALS}")

    if policy.keep_alive > timedelta(hours=24):
        found.append(f"keep-alive {policy.keep_alive} is past the 24 h burn-in limit")

    if policy.morning_start >= policy.morning_end:
        found.append("the morning window wraps midnight, which is not a morning")

    if _within(policy.morning_start, policy.quiet_start, policy.quiet_end):
        found.append("the morning window starts inside quiet hours and can never run")

    return tuple(found)


def _carried(dirty: Dirty) -> frozenset[str]:
    """Everything a full refresh puts on the glass that counts as news."""
    return frozenset(dirty.partial | dirty.full)


def _keep_alive_due(now: datetime, state: RefreshState, policy: Policy) -> bool:
    """Whether wall time says the panel is approaching the 24 h burn-in limit.

    Wall time, not monotonic, so that a reboot cannot lose the count - and a
    wall clock that has jumped *backwards* simply fails to fire, leaving the
    monotonic cadence to keep the panel alive on its own.
    """
    if state.last_full_at is None:
        return False
    return now - state.last_full_at >= policy.keep_alive


def _within(moment: time, start: time, end: time) -> bool:
    """Whether a local time falls in [start, end), wrapping over midnight.

    Half-open so that adjacent windows tile exactly: quiet hours end at 06:00
    and the morning window starts at 06:00, and 06:00 belongs to the morning.
    """
    if start == end:
        return False
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end
