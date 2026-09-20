"""Which bitmap in `assets/` a weather condition is drawn as.

A lookup, not a rule: the asset names are a property of this repository and the
condition names are a property of Home Assistant, so the mapping between them
belongs to the view rather than to the domain. `domain/format_da.py` maps the
same keys to Danish words; the two tables are deliberately separate because a
condition can gain a translation without gaining an icon, and the day it does,
the failure should be a placeholder in one place rather than a crash in both.

Night has its own icons for exactly two conditions, because those are the two
the assets cover: a clear sky and a partly clouded one. Rain at night looks
like rain. Where no night variant exists the day icon is correct, not a
compromise.

A condition this does not know returns None and the caller draws no icon.
`render/bmp.py` raises on a missing asset on purpose - an icon the code names
and the repository does not contain is a developer error, unlike a sensor that
has gone quiet - so guessing a filename here would turn a missing translation
into a crashed render.
"""

from __future__ import annotations

#: Home Assistant's conditions to the base name of a bitmap in
#: `assets/weather-icons/`. Every value here exists at both 50 and 100 px.
CONDITION_ICONS = {
    "clear-night": "weather-night",
    "cloudy": "weather-cloudy",
    "exceptional": "weather-cloudy-alert",
    "fog": "weather-fog",
    "hail": "weather-hail",
    "lightning": "weather-lightning",
    "lightning-rainy": "weather-lightning-rainy",
    "partlycloudy": "weather-partly-cloudy",
    "pouring": "weather-pouring",
    "rainy": "weather-rainy",
    "snowy": "weather-snowy",
    "snowy-rainy": "weather-snowy-rainy",
    "sunny": "weather-sunny",
    "windy": "weather-windy",
    "windy-variant": "weather-windy-variant",
}

#: The day icons that have a night counterpart, and what it is.
NIGHT_ICONS = {
    "weather-sunny": "weather-night",
    "weather-partly-cloudy": "weather-night-partly-cloudy",
}


def condition_icon(condition: str | None, night: bool | None = False) -> str | None:
    """The asset base name for a condition, or None if there is no icon for it.

    `night` is `derive.is_night()`'s answer and may be None, which means the sun
    entity did not say. An unknown sun is treated as day: a sun icon in the
    dark is a smaller lie than a moon at noon, and the condition text carries
    the real information either way.
    """
    if condition is None:
        return None

    icon = CONDITION_ICONS.get(condition.strip().lower())
    if icon is None:
        return None

    return NIGHT_ICONS.get(icon, icon) if night else icon
