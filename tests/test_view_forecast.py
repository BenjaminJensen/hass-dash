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

from domain.derive import temperature_scale
from domain.format_da import PLACEHOLDER
from domain.models import DailyPoint, HourlyPoint
from view.boxes import CURVE_AXIS_EVERY, CURVE_HOURS, CURVE_POINTS, curve_boxes, screen_boxes
from view.drawlist import (
    Align,
    Colour,
    Edge,
    Primitive,
    UpdateClass,
    inconsistent_regions,
    violations,
)
from view.forecast import LABEL_WIDTH, TICK_HEIGHT, curve, days

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
NOMINAL = hours([9 + min(index, 24 - index) * 0.75 for index in range(CURVE_POINTS)])

#: What the outdoor sensor says right now, which is not the forecast's problem.
NOW = 17.0


def draw_curve(hourly=NOMINAL, now=NOW):
    return curve(hourly, now, BOXES.curve)


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
        assert f"TEMPERATUR NÆSTE {CURVE_HOURS} TIMER" in text_of(draw_curve(), "curve.title")

    def test_it_reads_out_the_hour_the_line_starts_on(self):
        assert "NU 17°" in text_of(draw_curve(), "curve.title")

    def test_the_reading_is_the_sensor_rather_than_the_forecast(self):
        """The hero's number, repeated. The forecast's first hour is a forecast."""
        assert "NU 11°" in text_of(draw_curve(NOMINAL, 11.4), "curve.title")

    def test_a_missing_reading_is_a_placeholder_and_not_a_blank(self):
        assert f"NU {PLACEHOLDER}" in text_of(draw_curve(now=None), "curve.title")

    def test_a_placeholder_is_not_a_marker_and_spends_no_red(self):
        items = draw_curve(hourly=(), now=None)

        assert Colour.RED not in {item.colour for item in items}

    def test_the_reading_is_the_curves_one_red_thing_outside_the_rain(self):
        title = [item for item in draw_curve() if item.region == "curve.title"]

        assert [item.colour for item in title] == [Colour.BLACK, Colour.RED]


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

    def test_the_extremes_sit_inside_the_band_its_gridlines_bound(self):
        """The band rounds out to whole degrees now, so the line no longer
        touches its edges - it touches the gridlines that say why."""
        band = curve_boxes(BOXES.curve).line
        ys = [y for _, y in self.lines(draw_curve())[0].points]

        assert band.y <= min(ys) < max(ys) < band.bottom

    def test_a_flat_forecast_does_not_divide_by_zero(self):
        points = self.lines(draw_curve(hours([12.0] * 6)))[0].points

        assert len({y for _, y in points}) == 1

    def test_the_line_spans_the_plot_from_edge_to_edge(self):
        plot = curve_boxes(BOXES.curve).plot
        xs = [x for x, _ in self.lines(draw_curve())[0].points]

        assert min(xs) == plot.x
        assert max(xs) == plot.right - 1

    def test_the_hours_are_evenly_spaced_left_to_right(self):
        """To the pixel the rounding leaves over, which nobody can see."""
        xs = [x for x, _ in self.lines(draw_curve())[0].points]
        steps = {later - earlier for earlier, later in zip(xs, xs[1:])}

        assert max(steps) - min(steps) <= 1

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
        """The grid is geometry and survives; the scale and the hours do not."""
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
    def labels(self, items):
        return [item for item in items if item.region == "curve.axis"]

    def test_it_labels_every_third_hour_from_now_to_the_same_hour_tomorrow(self):
        assert len(text_of(draw_curve(), "curve.axis")) == CURVE_HOURS // CURVE_AXIS_EVERY + 1

    def test_the_labels_are_local_hours(self):
        """The forecast starts at 18.00 UTC, which is 20.00 in Copenhagen."""
        assert text_of(draw_curve(), "curve.axis") == [
            "20",
            "23",
            "02",
            "05",
            "08",
            "11",
            "14",
            "17",
            "20",
        ]

    def test_a_short_forecast_labels_only_the_hours_it_reached(self):
        """The gridlines above them are geometry; the labels are data."""
        assert text_of(draw_curve(hours([12.0] * 7)), "curve.axis") == ["20", "23", "02"]

    def test_a_label_is_centred_on_its_own_gridline(self):
        plot = curve_boxes(BOXES.curve).plot
        first, *_ = self.labels(draw_curve())

        assert first.align is Align.CENTER
        assert abs((first.box.x + first.box.right) // 2 - plot.x) <= 1

    def test_the_last_label_is_trimmed_rather_than_left_over_the_column_rule(self):
        column = BOXES.curve
        last = self.labels(draw_curve())[-1]

        assert last.box.right == column.right
        assert last.box.width < LABEL_WIDTH

    def test_the_labels_are_full_because_three_hourly_cannot_be_byte_aligned(self):
        """See view/boxes.py: 8 divides neither the pitch nor its half."""
        assert all(item.update is UpdateClass.FULL for item in self.labels(draw_curve()))


class TestTheGrid:
    def grid(self, items):
        return [item for item in items if item.primitive is Primitive.RULE and item.dash]

    def solid(self, items):
        return [item for item in items if item.primitive is Primitive.RULE and not item.dash]

    def test_the_plot_is_framed_left_and_below_and_nowhere_else(self):
        """An axis on two sides; a box would fence the data in."""
        assert {item.edge for item in self.solid(draw_curve())} == {Edge.LEFT, Edge.BOTTOM}

    def test_every_labelled_hour_but_the_first_carries_a_dotted_vertical(self):
        """The first is the plot's own left edge, and it is already solid."""
        verticals = [item for item in self.grid(draw_curve()) if item.edge is Edge.LEFT]

        assert len(verticals) == CURVE_HOURS // CURVE_AXIS_EVERY

    def test_the_verticals_are_drawn_whatever_the_forecast_said(self):
        assert len(self.grid(draw_curve(()))) == CURVE_HOURS // CURVE_AXIS_EVERY

    def test_each_gridline_of_the_scale_is_a_dotted_horizontal(self):
        _, _, ticks = temperature_scale(NOMINAL)
        horizontals = [item for item in self.grid(draw_curve()) if item.edge is Edge.TOP]

        assert len(horizontals) == len(ticks)

    def test_a_horizontal_spans_the_plot_and_a_vertical_stands_on_the_baseline(self):
        plot = curve_boxes(BOXES.curve).plot
        grid = self.grid(draw_curve())

        for item in grid:
            if item.edge is Edge.TOP:
                assert item.box.x == plot.x and item.box.right == plot.right
            else:
                assert item.box.y == plot.y and item.box.bottom == plot.bottom

    def test_the_grid_is_black_and_under_the_data(self):
        items = draw_curve(hours([12.0] * 4, precipitation=[1.0] * 4))
        grid = self.grid(items)

        assert {item.colour for item in grid} == {Colour.BLACK}
        assert items.index(grid[-1]) < min(
            index for index, item in enumerate(items) if item.primitive is Primitive.LINE
        )


class TestTheTickGutter:
    def test_it_labels_every_gridline_of_the_scale(self):
        _, _, ticks = temperature_scale(NOMINAL)

        assert text_of(draw_curve(), "curve.ticks") == [f"{tick}°" for tick in ticks]

    def test_the_labels_stay_in_the_gutter_beside_the_plot(self):
        gutter = curve_boxes(BOXES.curve).ticks
        labels = [item for item in draw_curve() if item.region == "curve.ticks"]

        assert all(item.box.x == gutter.x and item.box.right == gutter.right for item in labels)
        assert all(item.box.y >= gutter.y and item.box.bottom <= gutter.bottom for item in labels)

    def test_a_label_sits_on_the_line_it_names(self):
        boxes = curve_boxes(BOXES.curve)
        low, high, ticks = temperature_scale(NOMINAL)
        middle = boxes.line.bottom - 1 - (ticks[1] - low) / (high - low) * (boxes.line.height - 1)
        label = [item for item in draw_curve() if item.region == "curve.ticks"][1]

        assert abs((label.box.y + label.box.bottom) // 2 - middle) <= TICK_HEIGHT // 2

    def test_a_forecast_with_no_temperatures_has_no_scale_to_label(self):
        assert text_of(draw_curve(hours([None, None])), "curve.ticks") == []

    def test_the_gutter_keeps_the_partial_class_the_rest_of_the_curve_spent(self):
        """Black, and the one box here still aligned to 8."""
        labels = [item for item in draw_curve() if item.region == "curve.ticks"]

        assert all(item.update is UpdateClass.PARTIAL for item in labels)
        assert all(item.box.is_byte_aligned for item in labels)
        assert {item.colour for item in labels} == {Colour.BLACK}


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

    def test_only_the_tick_gutter_is_still_partial_eligible(self):
        """The plot holds red bars, the title holds a red reading, and the hour
        labels are no longer byte-aligned. One region, one update class."""
        classes = {item.region: item.update for item in draw_curve()}

        assert classes["curve.plot"] is UpdateClass.FULL
        assert classes["curve.title"] is UpdateClass.FULL
        assert classes["curve.axis"] is UpdateClass.FULL
        assert classes["curve.ticks"] is UpdateClass.PARTIAL

    def test_nothing_the_curve_draws_leaves_the_plot(self):
        wet = hours([9.0 + index for index in range(CURVE_POINTS)], [2.0] * CURVE_POINTS)
        plot = curve_boxes(BOXES.curve).plot

        for item in draw_curve(wet):
            if item.region != "curve.plot":
                continue
            assert item.box.x >= plot.x and item.box.right <= plot.right
            assert item.box.y >= plot.y and item.box.bottom <= plot.bottom
