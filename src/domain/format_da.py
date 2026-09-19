"""Danish formatting for one household's wall.

This is not a localisation framework and is not meant to become one. The
language is baked in deliberately (INTENT.md section 2): comma as decimal
separator, dot as time separator, Danish weekday and month names,
Europe/Copenhagen throughout.

Every formatter accepts None and returns PLACEHOLDER, so a dead sensor renders
as a neutral mark rather than crashing a layout function.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Copenhagen")

#: What a missing value looks like on the glass. An en dash, not a hyphen.
PLACEHOLDER = "–"

#: Monday-first, matching datetime.weekday().
WEEKDAYS = (
    "mandag",
    "tirsdag",
    "onsdag",
    "torsdag",
    "fredag",
    "lørdag",
    "søndag",
)

#: Three-letter forms for the seven-day strip, drawn uppercase.
WEEKDAYS_SHORT = ("MAN", "TIR", "ONS", "TOR", "FRE", "LØR", "SØN")

#: Indexed by month number, so index 0 is unused.
MONTHS = (
    "",
    "januar",
    "februar",
    "marts",
    "april",
    "maj",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "december",
)


def to_local(value: datetime | None) -> datetime | None:
    """Convert to Europe/Copenhagen.

    A naive datetime is assumed to already be local wall time and is labelled
    rather than shifted; an aware one is converted. Sources are expected to
    produce aware datetimes, so the naive branch is a courtesy, not a contract.
    """
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TZ)

    return value.astimezone(LOCAL_TZ)


def decimal(value: float | None, places: int = 1) -> str:
    """Format a number with a comma as the decimal separator."""
    if value is None:
        return PLACEHOLDER

    return f"{value:.{places}f}".replace(".", ",")


def temperature(value: float | None, places: int = 1) -> str:
    """A temperature with its degree sign: 23,1 degrees becomes "23,1°"."""
    if value is None:
        return PLACEHOLDER

    return f"{decimal(value, places)}°"


def humidity(value: float | None) -> str:
    """A relative humidity as whole percent: "44 %"."""
    if value is None:
        return PLACEHOLDER

    return f"{round(value)} %"


def pressure(value: float | None) -> str:
    """Air pressure in whole hectopascals."""
    if value is None:
        return PLACEHOLDER

    return f"{round(value)} hPa"


def wind_speed(value: float | None) -> str:
    """Wind speed in metres per second, one decimal."""
    if value is None:
        return PLACEHOLDER

    return f"{decimal(value, 1)} m/s"


def precipitation(value: float | None) -> str:
    """Precipitation in millimetres, one decimal."""
    if value is None:
        return PLACEHOLDER

    return f"{decimal(value, 1)} mm"


def clock(value: datetime | None) -> str:
    """Local time with a dot separator, as Danish writes it: "14.32"."""
    local = to_local(value)
    if local is None:
        return PLACEHOLDER

    return f"{local.hour:02d}.{local.minute:02d}"


def date_long(value: datetime | None) -> str:
    """The header's date: "Lørdag 19. september".

    Danish capitalises neither weekdays nor months mid-sentence; the weekday is
    capitalised here only because it opens the line.
    """
    local = to_local(value)
    if local is None:
        return PLACEHOLDER

    weekday = WEEKDAYS[local.weekday()]
    return f"{weekday.capitalize()} {local.day}. {MONTHS[local.month]}"


def weekday_short(value: datetime | None) -> str:
    """A day of the seven-day strip: "LØR"."""
    local = to_local(value)
    if local is None:
        return PLACEHOLDER

    return WEEKDAYS_SHORT[local.weekday()]
