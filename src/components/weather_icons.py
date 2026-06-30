"""Shared weather condition -> icon mapping helpers."""
from typing import Optional
import re


_ICON_MAP = {
    # Canonical HA keys (specific variants first)
    "lightning-rainy": "weather-lightning-rainy",
    "snowy-rainy": "weather-snowy-rainy",
    "windy-variant": "weather-windy-variant",
    "clear-night": "weather-night",
    # Canonical simple keys
    "lightning": "weather-lightning",
    "hail": "weather-hail",
    "pouring": "weather-pouring",
    "rainy": "weather-rainy",
    "snowy": "weather-snowy",
    "partlycloudy": "weather-partly-cloudy",
    "cloudy": "weather-cloudy",
    "fog": "weather-fog",
    "sunny": "weather-sunny",
    "windy": "weather-windy",
    "exceptional": "weather-cloudy-alert",
}


def _norm_alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


_NORMALIZED_ICON_MAP = {_norm_alnum(key): icon for key, icon in _ICON_MAP.items()}


def get_icon_for_condition(condition: Optional[str], is_night: bool = False) -> Optional[str]:
    """Map a Home Assistant weather condition to an icon base name."""
    icon = _NORMALIZED_ICON_MAP.get(_norm_alnum(condition or ""))
    if icon == "weather-partly-cloudy" and is_night:
        return "weather-night-partly-cloudy"
    return icon
