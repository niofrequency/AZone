#  This file is part of wger Workout Manager <https://github.com/wger-project>.
#  Copyright (C) wger Team
#
#  wger Workout Manager is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  wger Workout Manager is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Server-rendered SVG line charts for the coach pages.

wger's server-rendered pages ship no charting library, so the geometry is
computed here and drawn by templates/coach/_line_chart.html, with a small
script for the hover crosshair. Mark specs follow the dataviz rules: 2px
lines, >= 8px dots with a 2px surface ring, hairline recessive grid, one axis.
"""

# Standard Library
import datetime
import math
from dataclasses import (
    dataclass,
    field,
)
from decimal import Decimal

# wger
from wger.coach.body import Point


WIDTH = 640
HEIGHT = 240
MARGIN_LEFT = 48
MARGIN_RIGHT = 72
MARGIN_TOP = 16
MARGIN_BOTTOM = 28


@dataclass
class Series:
    key: str
    label: str
    points: list[Point]
    style: str = 'line'
    """'line', 'dots', 'bars' or 'reference'"""


@dataclass
class Chart:
    id: str
    title: str
    unit: str
    series: list[Series]
    decimals: int = 1
    reference_value: Decimal | None = None
    reference_label: str = ''

    width: int = WIDTH
    height: int = HEIGHT
    paths: list[dict] = field(default_factory=list)
    dots: list[dict] = field(default_factory=list)
    bars: list[dict] = field(default_factory=list)
    y_ticks: list[dict] = field(default_factory=list)
    x_ticks: list[dict] = field(default_factory=list)
    reference: dict | None = None
    end_label: dict | None = None
    hover: list[dict] = field(default_factory=list)
    legend: list[dict] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any(s.points for s in self.series if s.style != 'reference')

    @property
    def plot_left(self):
        return MARGIN_LEFT

    @property
    def plot_right(self):
        return self.width - MARGIN_RIGHT

    @property
    def plot_top(self):
        return MARGIN_TOP

    @property
    def plot_bottom(self):
        return self.height - MARGIN_BOTTOM

    @property
    def plot_width(self):
        return self.plot_right - self.plot_left

    @property
    def data_id(self):
        """Element id of the hover data"""
        return f'{self.id}-data'


def nice_step(span: float, target_ticks: int = 4) -> float:
    raw = span / max(target_ticks, 1)
    magnitude = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for multiple in (1, 2, 2.5, 5, 10):
        if raw <= multiple * magnitude:
            return multiple * magnitude
    return 10 * magnitude


def bar_path(x0: float, x1: float, top: float, base: float) -> str:
    """
    A bar with a 4px rounded top, square at the baseline
    """
    r = max(min(4, (x1 - x0) / 2, base - top), 0)
    x0, x1 = round(x0, 1), round(x1, 1)
    return (
        f'M{x0},{base} L{x0},{top + r} Q{x0},{top} {x0 + r},{top} '
        f'L{x1 - r},{top} Q{x1},{top} {x1},{top + r} L{x1},{base} Z'
    )


def fmt(value, decimals: int) -> str:
    return f'{float(value):,.{decimals}f}'


def build(chart: Chart) -> Chart:
    """
    Fills in the geometry of a chart from its series
    """
    data_points = [p for s in chart.series for p in s.points]
    if chart.is_empty:
        return chart

    values = [float(p.value) for p in data_points]
    if chart.reference_value is not None:
        values.append(float(chart.reference_value))
    has_bars = any(s.style == 'bars' and s.points for s in chart.series)
    if has_bars:
        # Bars grow from zero
        values.append(0)
    low, high = min(values), max(values)
    if high - low < 1e-9:
        low, high = low - 1, high + 1
    step = nice_step(high - low)
    y_min = math.floor(low / step) * step
    y_max = math.ceil(high / step) * step

    dates = [p.date for p in data_points]
    d_min, d_max = min(dates), max(dates)
    if has_bars:
        # Half a day of room so the outer bars aren't cut in half
        d_min -= datetime.timedelta(days=1)
        d_max += datetime.timedelta(days=1)
    if d_min == d_max:
        d_min -= datetime.timedelta(days=3)
        d_max += datetime.timedelta(days=3)
    total_days = (d_max - d_min).days

    def x(date: datetime.date) -> float:
        span = chart.plot_right - chart.plot_left
        return round(chart.plot_left + span * (date - d_min).days / total_days, 1)

    def y(value) -> float:
        span = chart.plot_bottom - chart.plot_top
        return round(chart.plot_bottom - span * (float(value) - y_min) / (y_max - y_min), 1)

    decimals = chart.decimals
    tick = y_min
    while tick <= y_max + step / 2:
        chart.y_ticks.append({'y': y(tick), 'label': fmt(tick, 0 if step >= 1 else decimals)})
        tick += step

    tick_count = min(5, total_days + 1)
    for i in range(tick_count):
        date = d_min + datetime.timedelta(days=round(total_days * i / max(tick_count - 1, 1)))
        chart.x_ticks.append({'x': x(date), 'label': date.strftime('%b %-d')})

    for series in chart.series:
        if not series.points:
            continue
        coords = [(x(p.date), y(p.value)) for p in series.points]
        if series.style == 'dots':
            chart.dots += [{'x': cx, 'y': cy, 'series': series.key} for cx, cy in coords]
        elif series.style == 'bars':
            slot = (chart.plot_right - chart.plot_left) / max(total_days, 1)
            width = min(24, slot * 0.6)
            base = y(0)
            for cx, cy in coords:
                chart.bars.append({'d': bar_path(cx - width / 2, cx + width / 2, cy, base)})
        else:
            d = 'M' + ' L'.join(f'{cx},{cy}' for cx, cy in coords)
            chart.paths.append({'d': d, 'series': series.key, 'style': series.style})
        chart.legend.append({'key': series.key, 'label': series.label, 'style': series.style})

    if chart.reference_value is not None:
        chart.reference = {
            'y': y(chart.reference_value),
            'label': chart.reference_label or fmt(chart.reference_value, decimals),
        }

    main = next(
        (s for s in chart.series if s.style == 'line' and s.points),
        next(s for s in chart.series if s.style != 'reference' and s.points),
    )
    last = main.points[-1]
    chart.end_label = {
        'x': x(last.date),
        'y': y(last.value),
        'label': f'{fmt(last.value, decimals)} {chart.unit}'.strip(),
        'dot': main.style != 'bars',
    }

    # Hover: one column per date with every series' value on that day
    by_date = {}
    for series in chart.series:
        for p in series.points:
            by_date.setdefault(p.date, {})[series.label] = fmt(p.value, decimals)
    chart.hover = [
        {'x': x(d), 'date': d.strftime('%a, %b %-d %Y'), 'values': by_date[d]}
        for d in sorted(by_date)
    ]
    return chart
