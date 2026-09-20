"""The curve and the day strip: what they plot, and where they refuse to.

The curve is the one region on the screen with computed geometry, so it gets
the only geometric assertions in the view tests - but they are about the
*mapping*, not about pixels: the warmest hour is at the top, the coldest at the
bottom, a missing hour breaks the line rather than being interpolated across,
and nothing ever leaves the plot. A font change touches none of it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from domain.format_da import PLACEHOLDER
from domain.models import DailyPoint, HourlyPoint
from view.boxes import CURVE_POINTS, curve_boxes, screen_boxes
from view.drawlist import (
    Colour,
    Primitive,
    UpdateClass,
    inconsistent_regions,
    violations,
)
from view.forecast import curve, days

UTC = timezone.utc
BOXES = screen_boxes().left
START = datetime(2026, 9, 19, 18, 0, tzinfo=UTC)


def hours(temperatures, precipitation=None, start=START):
    """An hourly forecast from a list of temperatures, one per hour."""
    rain = precipitation or [0.0] * len(temperatures)
    return tuple(
        HourlyPoint(time=start + timedelta(hours=index), temperature=value, precipitation=wet)
        for index, (value, wet) in enumerate(zip(temperatures, rain))
    )


#: A day that warms from 9 to 18 and cools back, which is what a curve is for.
NOMINAL = hours([9 + min(index, 24 - index) * 0.75 for index in range(24)])


def draw_curve(hourly=NOMINAL):
    return curve(hourly, BOXES.curve)


def draw_days(daily):
    return days(daily, BOXES.days)


def items_in(items, primitive):
    return [item for item in items if item.primitive is primitive]


def text_of(items, region):
    return [
        item.text for item in items if item.region == region and item.primitive is Primitive.TEXT
    ]


class TestTheCurveTitle:
    def test_it_says_how_far_forward_it_looks(self):
        """Not "today": the payload starts at the current hour. PLAN.md slice 2.2."""
        assert f"NÆSTE {CURVE_POINTS} TIMER" in text_of(draw_curve(), "curve.title")

    def test_it_states_the_range_the_plot_is_scaled_to(self):
        assert "9°–18°" in text_of(draw_curve(), "curve.title")

    def test_an_empty_forecast_states_a_range_of_placeholders(self):
        assert f"{PLACEHOLDER}–{PLACEHOLDER}" in text_of(draw_curve(()), "curve.title")


class TestTheCurveLine:
    def lines(self, items):
        return items_in(items, Primitive.LINE)

    def test_one_unbroken_forecast_is_one_line(self):
        assert len(self.lines(draw_curve())) == 1

    def test_it_plots_every_hour_it_was_given(self):
        assert len(self.lines(draw_curve())[0].points) == CURVE_POINTS

    def test_warm_is_up_and_cold_is_down(self):
        """The screen's y grows downward, so the warmest hour has the smallest y."""
        points = self.lines(draw_curve(hours([9.0, 18.0])))[0].points

        assert points[1][1] < points[0][1]

    def test_the_extremes_touch_the_edges_of_the_plot_band(self):
        band = curve_boxes(BOXES.curve).line
        ys = [y for _, y in self.lines(draw_curve())[0].points]

        assert min(ys) == band.y
        assert max(ys) == band.bottom - 1

    def test_a_flat_forecast_does_not_divide_by_zero(self):
        points = self.lines(draw_curve(hours([12.0] * 6)))[0].points

        assert len({y for _, y in points}) == 1

    def test_the_hours_are_evenly_spaced_left_to_right(self):
        xs = [x for x, _ in self.lines(draw_curve())[0].points]
        steps = {later - earlier for earlier, later in zip(xs, xs[1:])}

        assert len(steps) == 1

    def test_a_missing_hour_breaks_the_line_instead_of_being_drawn_through(self):
        """The forecast did not say what happens at 20.00. Nor does the screen."""
        broken = hours([9.0, 10.0, None, 12.0, 13.0])

        assert len(self.lines(draw_curve(broken))) == 2

    def test_an_isolated_reading_is_drawn_as_a_dot_rather_than_dropped(self):
        lonely = hours([None, 12.0, None])
        items = draw_curve(lonely)

        assert self.lines(items) == []
        assert any(
            item.primitive is Primitive.FILL and item.colour is Colour.BLACK for item in items
        )

    def test_a_forecast_with_no_temperatures_draws_no_line_at_all(self):
        assert self.lines(draw_curve(hours([None, None]))) == []

    def test_an_empty_forecast_is_a_legal_frame_with_a_title_and_nothing_else(self):
        items = draw_curve(())

        assert violations(items) == ()
        assert {item.region for item in items} == {"curve.title", "curve.plot"}


class TestPrecipitationBars:
    def bars(self, items):
        return [
            item for item in items if item.primitive is Primitive.FILL and item.colour is Colour.RED
        ]

    def test_a_wet_hour_gets_a_red_bar(self):
        wet = hours([12.0, 12.0, 12.0], precipitation=[0.0, 1.0, 0.0])

        assert len(self.bars(draw_curve(wet))) == 1

    def test_a_dry_forecast_spends_no_red(self):
        assert self.bars(draw_curve()) == []

    def test_more_rain_is_a_taller_bar(self):
        light = self.bars(draw_curve(hours([12.0], precipitation=[0.5])))[0]
        heavy = self.bars(draw_curve(hours([12.0], precipitation=[3.0])))[0]

        assert heavy.box.height > light.box.height

    def test_a_downpour_is_capped_at_the_band_rather_than_overflowing_it(self):
        band = curve_boxes(BOXES.curve).bars
        bar = self.bars(draw_curve(hours([12.0], precipitation=[40.0])))[0]

        assert bar.box.height == band.height
        assert bar.box.y >= band.y

    def test_a_trace_of_rain_is_still_visible(self):
        """A bar rounded down to nothing reads as a dry hour, which is a lie."""
        bar = self.bars(draw_curve(hours([12.0], precipitation=[0.05])))[0]

        assert bar.box.height >= 3

    def test_every_bar_grows_up_from_the_baseline(self):
        wet = hours([12.0] * 4, precipitation=[0.5, 2.0, 0.0, 4.0])
        band = curve_boxes(BOXES.curve).bars

        assert {bar.box.bottom for bar in self.bars(draw_curve(wet))} == {band.bottom}

    def test_the_first_and_last_bars_stay_inside_the_plot(self):
        wet = hours([12.0] * CURVE_POINTS, precipitation=[1.0] * CURVE_POINTS)
        plot = curve_boxes(BOXES.curve).plot
        bars = self.bars(draw_curve(wet))

        assert min(bar.box.x for bar in bars) >= plot.x
        assert max(bar.box.right for bar in bars) <= plot.right


class TestTheAxis:
    def test_it_labels_every_sixth_hour(self):
        assert len(text_of(draw_curve(), "curve.axis")) == CURVE_POINTS // 6

    def test_the_labels_are_local_hours(self):
        """The forecast starts at 18.00 UTC, which is 20.00 in Copenhagen."""
        assert text_of(draw_curve(), "curve.axis") == ["20", "02", "08", "14"]

    def test_the_labels_are_partial_eligible_and_therefore_byte_aligned(self):
        labels = [item for item in draw_curve() if item.region == "curve.axis"]

        assert all(item.update is UpdateClass.PARTIAL for item in labels)
        assert all(item.box.is_byte_aligned for item in labels)


class TestTheDayStrip:
    def daily(self, count, start=datetime(2026, 9, 19, 10, 0, tzinfo=UTC)):
        return tuple(
            DailyPoint(
                date=start + timedelta(days=index),
                condition="cloudy",
                temperature_high=18.0 - index,
                temperature_low=9.0 - index,
            )
            for index in range(count)
        )

    def test_it_draws_one_column_per_day(self):
        regions = {item.region for item in draw_days(self.daily(6))}

        assert regions == {f"day.{index}" for index in range(6)}

    def test_a_column_is_a_weekday_an_icon_and_a_high_over_a_low(self):
        items = [item for item in draw_days(self.daily(1)) if item.region == "day.0"]

        assert [item.primitive for item in items] == [
            Primitive.TEXT,
            Primitive.ICON,
            Primitive.TEXT,
        ]
        assert [item.text for item in items if item.primitive is Primitive.TEXT] == [
            "LØR",
            "18°/9°",
        ]

    def test_a_seventh_day_is_dropped_rather_than_drawn_off_the_panel(self):
        """This provider returns six; a richer one must not corrupt the strip."""
        assert "day.6" not in {item.region for item in draw_days(self.daily(7))}

    def test_a_day_the_forecast_does_not_reach_is_not_drawn_at_all(self):
        """An empty column with two dashes in it claims the provider said something."""
        regions = {item.region for item in draw_days(self.daily(2))}

        assert regions == {"day.0", "day.1"}

    def test_a_day_with_nothing_in_it_is_placeholders_and_no_icon(self):
        items = draw_days((DailyPoint(),))

        assert items_in(items, Primitive.ICON) == []
        assert text_of(items, "day.0") == [PLACEHOLDER, f"{PLACEHOLDER}/{PLACEHOLDER}"]

    def test_no_forecast_at_all_draws_nothing(self):
        assert draw_days(()) == ()

    def test_the_whole_strip_is_red_free_and_partial_eligible(self):
        items = draw_days(self.daily(6))

        assert Colour.RED not in {item.colour for item in items}
        assert {item.update for item in items} == {UpdateClass.PARTIAL}


class TestTheRefreshContract:
    #: Every shape of forecast the layout has to survive.
    INPUTS = (
        NOMINAL,
        hours([12.0] * CURVE_POINTS, precipitation=[3.0] * CURVE_POINTS),
        hours([9.0, None, 11.0, None, 13.0]),
        hours([None, None]),
        (),
    )

    @pytest.mark.parametrize("hourly", INPUTS)
    def test_every_forecast_produces_a_legal_draw_list(self, hourly):
        assert violations(draw_curve(hourly)) == ()

    def test_no_region_changes_its_update_class_with_the_forecast(self):
        assert inconsistent_regions([draw_curve(hourly) for hourly in self.INPUTS]) == ()

    def test_the_plot_is_full_only_because_the_bars_share_its_window(self):
        """One region, one update class - and red has no partial path."""
        classes = {item.region: item.update for item in draw_curve()}

        assert classes["curve.plot"] is UpdateClass.FULL
        assert classes["curve.title"] is UpdateClass.PARTIAL
        assert classes["curve.axis"] is UpdateClass.PARTIAL

    def test_nothing_the_curve_draws_leaves_the_plot(self):
        wet = hours([9.0 + index for index in range(CURVE_POINTS)], [2.0] * CURVE_POINTS)
        plot = curve_boxes(BOXES.curve).plot

        for item in draw_curve(wet):
            if item.region != "curve.plot":
                continue
            assert item.box.x >= plot.x and item.box.right <= plot.right
            assert item.box.y >= plot.y and item.box.bottom <= plot.bottom
