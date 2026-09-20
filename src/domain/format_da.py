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

#: Three-letter forms for the forecast day strip, drawn uppercase.
WEEKDAYS_SHORT = ("MAN", "TIR", "ONS", "TOR", "FRE", "LØR", "SØN")

#: Home Assistant's weather conditions, in Danish. The keys are the
#: integration's own vocabulary and are not ours to rename; the values are what
#: a Dane reads on a wall. `windy` and `windy-variant` differ only in how hard
#: it is blowing, which no Danish word distinguishes at this length.
CONDITIONS = {
    "clear-night": "Klar nat",
    "cloudy": "Skyet",
    "exceptional": "Ekstremt vejr",
    "fog": "Tåge",
    "hail": "Hagl",
    "lightning": "Torden",
    "lightning-rainy": "Torden og regn",
    "partlycloudy": "Delvist skyet",
    "pouring": "Kraftig regn",
    "rainy": "Regn",
    "snowy": "Sne",
    "snowy-rainy": "Slud",
    "sunny": "Sol",
    "windy": "Blæsende",
    "windy-variant": "Blæsende",
}

#: Eight points of the compass, Danish, clockwise from north. Eight rather than
#: sixteen because "ØNØ" on a wall at two metres is a smudge, and a coat
#: decision has never once turned on the difference.
COMPASS = ("N", "NØ", "Ø", "SØ", "S", "SV", "V", "NV")

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
    """A day of the forecast strip: "LØR"."""
    local = to_local(value)
    if local is None:
        return PLACEHOLDER

    return WEEKDAYS_SHORT[local.weekday()]


def condition(value: str | None) -> str:
    """A Home Assistant weather condition in Danish.

    An unrecognised condition renders as the placeholder rather than as its raw
    key: `windy-variant` on the wall is worse than a dash, because a dash says
    "no reading" and a key says "this dashboard is broken".
    """
    if value is None:
        return PLACEHOLDER

    return CONDITIONS.get(value.strip().lower(), PLACEHOLDER)


def wind_direction(bearing: float | None) -> str:
    """The compass point a wind bearing falls in: 237 degrees is "SV".

    The bearing is the direction the wind blows *from*, as meteorology and Home
    Assistant both report it, so a westerly reads "V" and that is what it means
    on the forecast too.
    """
    if bearing is None:
        return PLACEHOLDER

    sector = int((bearing % 360) / 45 + 0.5) % len(COMPASS)
    return COMPASS[sector]


def hour(value: datetime | None) -> str:
    """An axis label on the temperature curve: the local hour, two digits."""
    local = to_local(value)
    if local is None:
        return PLACEHOLDER

    return f"{local.hour:02d}"
