"""Condition to asset name, and the one thing that must never drift.

`render/bmp.py` raises on an icon file that does not exist, on purpose - an
asset the code names and the repository does not contain is a developer error,
not a dead sensor. So the assertion that matters most here is not about any
single condition: it is that every name this table can produce is a file on
disk, at both sizes the layout uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from render.bmp import ICON_DIR
from view.boxes import DAY_ICON_SIZE, HERO_ICON_SIZE
from view.icons import CONDITION_ICONS, NIGHT_ICONS, condition_icon


class TestMapping:
    @pytest.mark.parametrize(
        ("condition", "icon"),
        [
            ("sunny", "weather-sunny"),
            ("cloudy", "weather-cloudy"),
            ("partlycloudy", "weather-partly-cloudy"),
            ("lightning-rainy", "weather-lightning-rainy"),
            ("snowy-rainy", "weather-snowy-rainy"),
            ("exceptional", "weather-cloudy-alert"),
        ],
    )
    def test_a_condition_maps_to_its_asset(self, condition, icon):
        assert condition_icon(condition) == icon

    def test_case_and_surrounding_space_do_not_matter(self):
        assert condition_icon(" Sunny ") == "weather-sunny"

    def test_an_unknown_condition_has_no_icon(self):
        """None, so the caller draws nothing - never a guessed filename."""
        assert condition_icon("meteor-shower") is None

    def test_no_condition_has_no_icon(self):
        assert condition_icon(None) is None


class TestNight:
    def test_the_sun_becomes_a_moon_after_dark(self):
        assert condition_icon("sunny", night=True) == "weather-night"

    def test_partly_cloudy_has_its_own_night_variant(self):
        assert condition_icon("partlycloudy", night=True) == "weather-night-partly-cloudy"

    def test_rain_at_night_still_looks_like_rain(self):
        """Only two conditions have a night asset. The rest are already correct."""
        assert condition_icon("rainy", night=True) == "weather-rainy"

    def test_an_unknown_sun_is_treated_as_day(self):
        """derive.is_night() returns None when the sun entity did not say."""
        assert condition_icon("sunny", night=None) == "weather-sunny"

    def test_clear_night_is_a_moon_whatever_the_sun_entity_thinks(self):
        assert condition_icon("clear-night") == "weather-night"


class TestTheAssetsExist:
    """Every name this module can return, at both sizes, as a file."""

    def every_icon(self) -> set[str]:
        return set(CONDITION_ICONS.values()) | set(NIGHT_ICONS.values())

    @pytest.mark.parametrize("size", [HERO_ICON_SIZE, DAY_ICON_SIZE])
    def test_every_mapped_icon_is_on_disk_at_the_sizes_the_layout_uses(self, size):
        missing = [
            name
            for name in sorted(self.every_icon())
            if not (Path(ICON_DIR) / f"{name}-{size}x{size}.bmp").is_file()
        ]

        assert missing == []

    def test_the_night_table_only_renames_icons_the_day_table_produces(self):
        """A night variant of an icon nothing maps to is dead weight."""
        assert set(NIGHT_ICONS) <= set(CONDITION_ICONS.values())
