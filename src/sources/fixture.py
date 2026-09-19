"""Replays recorded Home Assistant payloads, including the unpleasant ones.

This is the source the dashboard is developed against (INTENT.md section 7).
It reads the same three files `tools/capture_snapshot.py` writes, so a set
recorded from the live instance and a set written by hand to be horrible are
interchangeable - which is the point. The hostile sets under
`tests/fixtures/sets/` could never come off a live capture, and the nominal
recording could never be invented accurately.

A missing *directory* is whole-source failure and raises `SourceUnavailable`,
because a fixture source with nothing to replay is a mistake in how the app was
launched. A missing *file* inside a present directory is not: an instance whose
weather integration is down returns no forecast, and the fixture set says so by
leaving the file out.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.house import HouseConfig
from domain.models import Snapshot
from sources.mapping import build_snapshot
from sources.port import SourceUnavailable

STATES_FILE = "states.json"
HOURLY_FILE = "forecast_hourly.json"
DAILY_FILE = "forecast_daily.json"

#: Where `tools/capture_snapshot.py` writes, resolved from this module.
DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


class FixtureSource:
    """A `SnapshotSource` backed by recorded JSON on disk."""

    def __init__(
        self,
        config: HouseConfig,
        directory: str | Path | None = None,
        clock: Any = None,
    ) -> None:
        self.config = config
        self.directory = Path(directory) if directory is not None else DEFAULT_FIXTURES
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def name(self) -> str:
        return f"fixture:{self.directory.name}"

    def fetch(self) -> Snapshot:
        """Replay the recorded payloads as one snapshot."""
        if not self.directory.is_dir():
            raise SourceUnavailable(f"no fixture directory at {self.directory}")

        errors: list[str] = []
        states = self._load(STATES_FILE, errors, required=True)
        hourly = self._load(HOURLY_FILE, errors)
        daily = self._load(DAILY_FILE, errors)

        return build_snapshot(
            self.config,
            states=self._by_entity_id(states),
            hourly=hourly,
            daily=daily,
            taken_at=self._clock(),
            extra_errors=tuple(errors),
        )

    def _load(self, filename: str, errors: list[str], required: bool = False) -> Any:
        """One payload file, or None with the reason recorded.

        Unreadable JSON is reported and then ignored. A fixture set that has
        been hand-edited into invalid JSON should still produce a screen full
        of placeholders, because that is what it would look like on the wall.
        """
        path = self.directory / filename
        if not path.exists():
            if required:
                raise SourceUnavailable(f"no {filename} in {self.directory}")
            errors.append(f"{filename}: not recorded in this fixture set")
            return None

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"{filename}: could not be read ({error})")
            return None

    @staticmethod
    def _by_entity_id(states: Any) -> Any:
        """Accept both shapes a recording can have.

        `capture_snapshot.py` writes a mapping keyed by entity id, but
        `/api/states` itself returns a list. Hand-written sets use whichever is
        more readable, so both are indexed here.
        """
        if isinstance(states, list):
            return {
                entry["entity_id"]: entry
                for entry in states
                if isinstance(entry, dict) and isinstance(entry.get("entity_id"), str)
            }
        return states
