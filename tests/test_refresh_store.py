"""PLAN.md M8.4: what a restart may and may not forget.

The thing being prevented is specific. The 180 s floor already stops a process
that restarts inside three minutes. What it does not stop is one that restarts
every four: without a file to read, each new process has fresh state, calls
that a first frame, and spends 26 seconds of high-voltage refresh on it - for
as long as the fault lasts. So the tests here are mostly about a second process
inheriting the first one's obligations, and about the one case where it must
*not*: a reboot, after which the monotonic clock has restarted and its old
readings mean nothing.

The boot id is injected rather than read, so the reboot case is testable at
all. `boot_id()` itself gets its own small test against a real file.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from domain.format_da import LOCAL_TZ
from refresh.policy import DEFAULT_POLICY, Refresh, RefreshState, decide
from refresh.store import VERSION, RefreshStore, boot_id

BOOT = "5e0bc3f2-0f0e-4a4a-9c2f-7f1a1b2c3d4e"
OTHER_BOOT = "00000000-1111-2222-3333-444444444444"
NOON = datetime(2026, 9, 20, 12, 0, tzinfo=LOCAL_TZ)


@pytest.fixture
def store(tmp_path):
    return RefreshStore(tmp_path / "refresh.json", BOOT)


def drawn(monotonic: float = 1000.0, at: datetime = NOON) -> RefreshState:
    """The state a full refresh leaves behind."""
    return RefreshState(
        last_refresh_monotonic=monotonic,
        last_full_monotonic=monotonic,
        last_full_at=at,
        partials_since_full=0,
    )


class TestARoundTrip:
    def test_a_state_survives_being_written_and_read(self, store):
        store.save(drawn())

        assert store.load(monotonic=1200.0) == drawn()

    def test_a_partial_count_survives_too(self, store):
        store.save(
            RefreshState(
                last_refresh_monotonic=1300.0,
                last_full_monotonic=1000.0,
                last_full_at=NOON,
                partials_since_full=3,
            )
        )

        assert store.load(monotonic=1400.0).partials_since_full == 3

    def test_the_wall_timestamp_keeps_its_zone(self, store):
        """The keep-alive subtracts it from an aware `now`, and Python raises
        on comparing that with a naive value."""
        store.save(drawn())

        restored = store.load(monotonic=1200.0).last_full_at
        assert restored is not None
        assert restored.tzinfo is not None
        assert restored == NOON

    def test_the_file_is_small_and_readable(self, store):
        store.save(drawn())

        record = json.loads(store.path.read_text(encoding="utf-8"))
        assert record["version"] == VERSION
        assert record["boot"] == BOOT
        assert store.path.stat().st_size < 400

    def test_nothing_is_left_beside_it(self, store):
        """Written to a neighbour and renamed over, so a power cut cannot leave
        a half-written file where `load()` expects a whole one."""
        store.save(drawn())
        store.save(drawn(2000.0))

        assert [path.name for path in store.path.parent.iterdir()] == ["refresh.json"]

    def test_it_makes_the_directory_it_was_pointed_at(self, tmp_path):
        store = RefreshStore(tmp_path / "var" / "lib" / "refresh.json", BOOT)
        store.save(drawn())

        assert store.path.is_file()


class TestWhatARestartInherits:
    def test_a_second_process_does_not_call_itself_a_first_frame(self, store):
        """The whole point. A fresh state means a full refresh at once; a
        restored one waits for the cadence like any other tick."""
        store.save(drawn(monotonic=1000.0))

        state = store.load(monotonic=1400.0)
        decision = decide(NOON + timedelta(minutes=7), 1400.0, state)

        assert decision.refresh is Refresh.NONE

    def test_a_crash_loop_cannot_re_flash_the_panel(self, store):
        """Ten restarts across half an hour, each one loading, deciding and -
        if it drew - saving. The vendor's 30-minute cadence should produce one
        refresh, not ten."""
        store.save(drawn(monotonic=0.0, at=NOON))
        refreshes = 0

        for restart in range(10):
            monotonic = 200.0 * (restart + 1)
            now = NOON + timedelta(seconds=monotonic)
            state = store.load(monotonic)
            decision = decide(now, monotonic, state)
            if decision.refreshes:
                refreshes += 1
                store.save(
                    RefreshState(monotonic, monotonic, now, 0)
                    if decision.refresh is Refresh.FULL
                    else state
                )

        assert refreshes == 1

    def test_the_floor_survives_a_restart_inside_it(self, store):
        store.save(drawn(monotonic=1000.0))

        state = store.load(monotonic=1060.0)

        assert decide(NOON, 1060.0, state).refresh is Refresh.NONE

    def test_the_keep_alive_survives_a_restart(self, store):
        """The one rule measured on wall time, because it is the one that has
        to outlive a monotonic clock (HARDWARE.md section 6)."""
        store.save(drawn(monotonic=1000.0, at=NOON))

        state = store.load(monotonic=1400.0)
        decision = decide(NOON + timedelta(hours=25), 1400.0, state)

        assert decision.refresh is Refresh.FULL


class TestWhatARebootDoesNotInherit:
    def test_a_different_boot_discards_the_monotonic_readings(self, tmp_path):
        """They counted from a boot that has ended. Comparing them against the
        new clock would be arithmetic on two different origins."""
        RefreshStore(tmp_path / "refresh.json", BOOT).save(drawn(monotonic=90000.0))

        state = RefreshStore(tmp_path / "refresh.json", OTHER_BOOT).load(monotonic=12.0)

        assert state.last_full_monotonic is None

    def test_a_reboot_still_waits_out_the_floor_once(self, tmp_path):
        """Assumed rather than calculated: after a reboot there is no clock
        that can say how long ago the last refresh was, and the panel is
        holding its previous image the whole time, so three minutes of patience
        costs a slightly staler frame and buys a floor that no fast reboot can
        cross."""
        RefreshStore(tmp_path / "refresh.json", BOOT).save(drawn(monotonic=90000.0))
        store = RefreshStore(tmp_path / "refresh.json", OTHER_BOOT)

        state = store.load(monotonic=12.0)

        assert decide(NOON, 12.0, state).refresh is Refresh.NONE
        assert decide(NOON, 12.0 + DEFAULT_POLICY.floor_seconds, state).refresh is Refresh.FULL

    def test_a_reboot_keeps_the_keep_alive(self, tmp_path):
        RefreshStore(tmp_path / "refresh.json", BOOT).save(drawn(at=NOON))

        state = RefreshStore(tmp_path / "refresh.json", OTHER_BOOT).load(monotonic=12.0)

        assert state.last_full_at == NOON

    def test_a_kernel_that_offers_no_boot_id_is_treated_as_a_reboot(self, tmp_path):
        """`None` means "cannot prove the clock is the same one", which is the
        same answer as "it is not"."""
        RefreshStore(tmp_path / "refresh.json", BOOT).save(drawn(monotonic=90000.0))

        state = RefreshStore(tmp_path / "refresh.json", None).load(monotonic=12.0)

        assert state.last_full_monotonic is None

    def test_a_reading_from_the_future_is_not_trusted(self, tmp_path):
        """A forward-only counter cannot produce one, so the file came from
        somewhere else - and restoring it would park the floor in the future
        and stop the panel permanently."""
        RefreshStore(tmp_path / "refresh.json", BOOT).save(drawn(monotonic=90000.0))

        state = RefreshStore(tmp_path / "refresh.json", BOOT).load(monotonic=100.0)

        assert state.last_full_monotonic is None
        assert state.last_refresh_monotonic == 100.0


class TestWhenTheFileIsNotThereOrNotRight:
    def test_no_file_is_a_first_frame(self, store):
        assert store.load(monotonic=10.0) == RefreshState()

    def test_a_first_frame_is_drawn_at_once(self, store):
        assert decide(NOON, 10.0, store.load(10.0)).refresh is Refresh.FULL

    def test_a_truncated_file_is_no_file(self, store, caplog):
        """What a power cut mid-write would leave, if the write were not
        atomic. It must not be what stops the dashboard starting."""
        store.path.write_text('{"version": 1, "boot": "5e0', encoding="utf-8")

        assert store.load(monotonic=10.0) == RefreshState()
        assert "unreadable" in caplog.text

    def test_a_file_holding_something_else_entirely_is_no_file(self, store):
        store.path.write_text("[1, 2, 3]", encoding="utf-8")

        assert store.load(monotonic=10.0) == RefreshState()

    def test_a_file_from_another_version_is_no_file(self, store, caplog):
        """So that adding a field later cannot make a stale file read as though
        it had one."""
        store.path.write_text(json.dumps({"version": VERSION + 1, "boot": BOOT}), encoding="utf-8")

        assert store.load(monotonic=10.0) == RefreshState()
        assert "version" in caplog.text

    def test_a_directory_where_the_file_should_be_is_no_file(self, tmp_path):
        (tmp_path / "refresh.json").mkdir()

        assert RefreshStore(tmp_path / "refresh.json", BOOT).load(10.0) == RefreshState()

    @pytest.mark.parametrize("value", ["not a time", "2026-09-20T12:00:00", 17, None, True])
    def test_a_timestamp_that_is_not_one_is_dropped(self, store, value):
        """Naive included: the keep-alive compares it against an aware `now`,
        and Python raises on that - a crash in the one rule that exists to
        prevent burn-in."""
        store.path.write_text(
            json.dumps({"version": VERSION, "boot": BOOT, "last_full_at": value}),
            encoding="utf-8",
        )

        assert store.load(monotonic=10.0).last_full_at is None

    @pytest.mark.parametrize("value", ["1000", None, True, [1000]])
    def test_a_clock_reading_that_is_not_a_number_is_dropped(self, store, value):
        store.path.write_text(
            json.dumps(
                {
                    "version": VERSION,
                    "boot": BOOT,
                    "last_refresh_monotonic": value,
                    "last_full_monotonic": value,
                }
            ),
            encoding="utf-8",
        )

        state = store.load(monotonic=10.0)

        assert state.last_refresh_monotonic is None
        assert state.last_full_monotonic is None


class TestTheBootId:
    def test_it_reads_the_kernels_answer(self, tmp_path):
        path = tmp_path / "boot_id"
        path.write_text(f"{BOOT}\n", encoding="utf-8")

        assert boot_id(path) == BOOT

    def test_a_missing_file_is_not_an_error(self, tmp_path):
        assert boot_id(tmp_path / "nothing") is None

    def test_an_empty_file_is_not_an_answer(self, tmp_path):
        path = tmp_path / "boot_id"
        path.write_text("\n", encoding="utf-8")

        assert boot_id(path) is None

    def test_at_stamps_the_store_with_this_machines_answer(self, tmp_path):
        """On Linux this is a real uuid; elsewhere it is `None`, and the store
        then treats every start as a reboot."""
        store = RefreshStore.at(tmp_path / "refresh.json")

        assert store.boot == boot_id()
