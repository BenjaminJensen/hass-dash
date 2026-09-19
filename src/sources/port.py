"""The seam between the dashboard and whatever is feeding it.

One method, one `Snapshot`, one cycle. Everything the screen needs arrives in a
single value taken at a single instant, so a render can never show half of one
reading and half of the next.

Two kinds of failure live here, and keeping them apart is the point of this
module:

*Per-entity failure is not failure.* A dead Zigbee sensor, a renamed entity, a
value that arrived as the string `unavailable` - each of those yields `None` in
the snapshot and is recorded in `Snapshot.source_errors`. `fetch()` still
returns. INTENT.md section 2: absence is a state, not a crash.

*Whole-source failure is failure.* If the instance cannot be reached at all,
there is no snapshot to return and inventing an empty one would blank the
screen with confident-looking placeholders. `fetch()` raises
`SourceUnavailable` instead, and the caller keeps showing the last good frame.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.models import Snapshot


class SourceUnavailable(Exception):
    """The source could not produce a snapshot at all.

    Raised for whole-source failure - the network is down, the token expired,
    the fixture directory is not there. Never raised because one sensor is
    quiet; that is what `Snapshot.source_errors` is for.
    """


@runtime_checkable
class SnapshotSource(Protocol):
    """Anything that can produce one `Snapshot` per refresh cycle."""

    #: Short identifier for logs, so a line says which source produced a frame.
    name: str

    def fetch(self) -> Snapshot:
        """One snapshot, or `SourceUnavailable` if there is nothing to give."""
        ...
