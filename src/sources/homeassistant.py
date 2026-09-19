"""The REST adapter. The only module in the project that makes a request.

Three calls per cycle: one `GET /api/states`, and the forecast service twice.
Fetching every state at once rather than one entity at a time is deliberate -
eleven rooms would otherwise be two dozen round trips, and the readings would
be smeared across however long that took. One snapshot means one instant.

Only the standard library is used. `homeassistant_api`, which the retired
client depended on, brought a dependency tree and a context manager for what is
two HTTP calls, and hid the failure modes this layer exists to handle.

On failure this module is quiet upward and loud in the snapshot: a forecast
that will not load leaves an empty strip and a line in `source_errors`, and
only an unreachable instance raises (see `port.py`).
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from config.house import HouseConfig
from domain.models import Snapshot
from sources.mapping import build_snapshot
from sources.port import SourceUnavailable

DEFAULT_TIMEOUT = 20.0

#: `weather.get_forecast` became `weather.get_forecasts` and the result moved
#: under the entity id. It has moved once, so the shape is dug for rather than
#: assumed - see `_forecast_list`.
FORECAST_SERVICE = "/api/services/weather/get_forecasts?return_response=true"


class HomeAssistantSource:
    """A `SnapshotSource` backed by a live Home Assistant instance."""

    def __init__(
        self,
        config: HouseConfig,
        base_url: str,
        token: str,
        timeout: float = DEFAULT_TIMEOUT,
        opener: Any = None,
    ) -> None:
        self.config = config
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        # Injected in tests so the suite never opens a socket.
        self._open = opener or urllib.request.urlopen

    @property
    def name(self) -> str:
        return f"hass:{self.base_url}"

    def fetch(self) -> Snapshot:
        """One snapshot from the live instance."""
        errors: list[str] = []
        states = self._states()
        hourly = self._forecast("hourly", errors)
        daily = self._forecast("daily", errors)

        return build_snapshot(
            self.config,
            states=states,
            hourly=hourly,
            daily=daily,
            taken_at=datetime.now(timezone.utc),
            extra_errors=tuple(errors),
        )

    # ----------------------------------------------------------------------
    # The two calls
    # ----------------------------------------------------------------------

    def _states(self) -> dict[str, dict]:
        """Every visible entity, keyed by id.

        This one is allowed to raise. If the instance will not say what any
        entity is doing there is no snapshot to build, and a screen full of
        placeholders would be a confident lie where the last good frame is the
        truth as of a few minutes ago.
        """
        try:
            payload = self._request("/api/states")
        except SourceUnavailable:
            raise
        except Exception as error:  # noqa: BLE001 - deliberately total
            raise SourceUnavailable(f"could not read states: {error}") from error

        if not isinstance(payload, list):
            raise SourceUnavailable("/api/states did not return a list of entities")

        return {
            entry["entity_id"]: entry
            for entry in payload
            if isinstance(entry, dict) and isinstance(entry.get("entity_id"), str)
        }

    def _forecast(self, kind: str, errors: list[str]) -> list:
        """The hourly or daily forecast, or an empty list and a recorded reason.

        A forecast failure is per-entity failure: the rooms are still worth
        showing even when the weather strip cannot be drawn.
        """
        try:
            response = self._request(
                FORECAST_SERVICE,
                payload={"entity_id": self.config.weather.entity_id, "type": kind},
            )
        except Exception as error:  # noqa: BLE001 - deliberately total
            errors.append(f"{kind} forecast: {error}")
            return []

        forecast = _forecast_list(response, self.config.weather.entity_id)
        if forecast is None:
            errors.append(f"{kind} forecast: unrecognised response shape")
            return []
        return forecast

    def _request(self, path: str, payload: dict | None = None) -> Any:
        """One authenticated call. POST when there is a body, otherwise GET."""
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST" if body is not None else "GET",
        )

        try:
            with self._open(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise SourceUnavailable(f"HTTP {error.code} from {path}") from error
        except (urllib.error.URLError, socket.timeout, OSError) as error:
            raise SourceUnavailable(f"could not reach {self.base_url}: {error}") from error

        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise SourceUnavailable(f"{path} did not return JSON: {error}") from error


def _forecast_list(response: Any, entity_id: str) -> list | None:
    """Dig the forecast list out of whatever the service wrapped it in.

    Returns None when nothing list-shaped can be found, which is reported, as
    distinct from an empty list, which is a legitimate answer from a provider
    that has no forecast to give.
    """
    if isinstance(response, list):
        return response
    if not isinstance(response, dict):
        return None

    # The current shape: {"service_response": {"weather.home": {"forecast": [...]}}}
    scope = response.get("service_response", response)
    if not isinstance(scope, dict):
        return None

    entry = scope.get(entity_id, scope)
    if isinstance(entry, dict):
        forecast = entry.get("forecast")
        if isinstance(forecast, list):
            return forecast

    # Older shape, and the single-entity case: {"forecast": [...]}
    forecast = scope.get("forecast")
    return forecast if isinstance(forecast, list) else None
