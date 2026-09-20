"""The part of the refresh state that has to survive the process.

`policy.py` is pure and stays that way; this is the small amount of I/O that
makes its arithmetic true across a restart. It exists because of one sentence
in PLAN.md M8.4: a restart loop must not be able to violate the 180 s floor or
lose the 24 h keep-alive.

**A crash loop is the case this is for.** The floor already stops a process
that restarts in under three minutes. What it does not stop is one that
restarts every four: each new process starts with a fresh `RefreshState`, calls
that a first frame, and spends 26 seconds of high-voltage refresh on it - for
as long as the fault lasts. Restoring `last_full_monotonic` is what makes the
second process wait for the cadence like any other tick.

**Two clocks, persisted differently, because only one of them survives a
reboot.** `time.monotonic()` on Linux counts from boot, so its readings stay
comparable across a *process* restart and become meaningless across a *machine*
restart. The file therefore records which boot wrote it - the kernel's own
`boot_id` - and the monotonic readings are restored only when that matches.

`last_full_at` is wall time and is restored either way. The board has no RTC
(HARDWARE.md section 6), so the value may be compared against a clock that has
jumped; `_keep_alive_due()` is written to fail closed on a backwards jump, and
the monotonic cadence keeps the panel alive on its own while NTP lands.

**After a reboot the floor is assumed, not calculated.** A boot the file does
not recognise restores no monotonic reading and instead marks *now* as the last
refresh, so the first frame waits one full floor interval. The panel is holding
its previous image the whole time - that is what e-paper does - so the cost is
a frame that is three minutes staler than it could have been, and the thing
bought is that no reboot, however fast, can write to the panel inside the
vendor's floor. Where the risk is unrepairable hardware damage, the pessimistic
reading is the right one.

**The file is small, written only after a refresh, and never fatal.** Roughly
200 bytes, and roughly 40 writes a day at the default cadence - which is what
allows it to sit on the SD card without being the thing that wears it out. A
file that cannot be read, or that has been corrupted by a power cut mid-write,
yields fresh state and a line in the log rather than a dashboard that will not
start.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from refresh.policy import RefreshState

logger = logging.getLogger("dash.state")

#: The kernel's identifier for this boot. Regenerated on every boot and
#: readable without privileges, which is exactly the question being asked: are
#: the monotonic readings in this file from the same clock I am reading now?
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")

#: The format version, so that a future field can be added without a stale file
#: being read as though it had one. An unknown version is treated as no file.
VERSION = 1


def boot_id(path: Path = BOOT_ID) -> str | None:
    """This boot's identity, or `None` where the kernel does not offer one.

    `None` is not an error and not a crash: it means "cannot prove the clock is
    the same one", which the loader treats exactly like a different boot. macOS
    and some containers land here, and so does a hardened kernel.
    """
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


@dataclass(frozen=True)
class RefreshStore:
    """Where the last refresh is written down, and how it is read back."""

    path: Path
    boot: str | None = None

    @classmethod
    def at(cls, path: str | Path) -> RefreshStore:
        """A store at `path`, stamped with the running kernel's boot id."""
        return cls(Path(path), boot_id())

    def load(self, monotonic: float) -> RefreshState:
        """The state a process should start from, given the clock it has.

        `monotonic` is the current reading, needed because a boot this file
        does not recognise starts the floor from now rather than from a number
        that no longer means anything.
        """
        record = self._read()
        if record is None:
            return RefreshState()

        last_full_at = _time(record.get("last_full_at"))

        if not self._same_boot(record, monotonic):
            logger.info("state=restored clocks=stale floor=assumed")
            return RefreshState(
                last_refresh_monotonic=monotonic,
                last_full_at=last_full_at,
            )

        logger.info("state=restored clocks=live")
        return RefreshState(
            last_refresh_monotonic=_number(record.get("last_refresh_monotonic")),
            last_full_monotonic=_number(record.get("last_full_monotonic")),
            last_full_at=last_full_at,
            partials_since_full=int(_number(record.get("partials_since_full")) or 0),
        )

    def save(self, state: RefreshState) -> None:
        """Write the state, atomically, so a power cut cannot truncate it.

        Written to a neighbouring temporary file and renamed over the target,
        because `os.replace()` is atomic within a filesystem and a half-written
        JSON file is precisely the corruption `load()` would then have to
        tolerate. Raises on failure; the caller decides that a dashboard which
        cannot write its state is still a dashboard.
        """
        payload = {
            "version": VERSION,
            "boot": self.boot,
            "last_refresh_monotonic": state.last_refresh_monotonic,
            "last_full_monotonic": state.last_full_monotonic,
            "last_full_at": state.last_full_at.isoformat() if state.last_full_at else None,
            "partials_since_full": state.partials_since_full,
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.new")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def _read(self) -> dict | None:
        """The file as a mapping, or `None` if there is nothing usable in it."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return None

        try:
            record = json.loads(text)
        except ValueError:
            logger.warning("state=unreadable path=%s", self.path)
            return None

        if not isinstance(record, dict):
            logger.warning("state=unreadable path=%s", self.path)
            return None

        if record.get("version") != VERSION:
            logger.warning("state=version path=%s", self.path)
            return None

        return record

    def _same_boot(self, record: dict, monotonic: float) -> bool:
        """Whether this file's monotonic readings are still comparable.

        Two ways to answer no. The boot id may differ, or be missing on either
        side - the ordinary reboot. Or a reading may be *ahead* of the clock
        being compared against, which a forward-only counter cannot produce and
        which therefore means the file came from somewhere else: restoring it
        would park the floor in the future and stop the panel for good.
        """
        if self.boot is None or record.get("boot") != self.boot:
            return False

        readings = (
            _number(record.get("last_refresh_monotonic")),
            _number(record.get("last_full_monotonic")),
        )
        return all(reading is None or reading <= monotonic for reading in readings)


def _number(value: object) -> float | None:
    """A float, or `None` for anything that is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _time(value: object) -> datetime | None:
    """An aware timestamp, or `None` for anything that is not one.

    Naive values are rejected rather than localised. The keep-alive subtracts
    this from an aware `now`, and Python raises on that comparison - so a naive
    value on disk would be a crash in the one rule that exists to prevent
    burn-in.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
