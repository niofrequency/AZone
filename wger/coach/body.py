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
Body tracking for the coach: the measurement categories a check-in writes to,
saving a check-in, and reading the history back as chart series.

Everything is stored in wger's own tables (measurements and gallery), so the
data also shows up in the regular measurement and gallery pages and the app.
"""

# Standard Library
import datetime
from collections import defaultdict
from dataclasses import (
    dataclass,
    field,
)
from decimal import Decimal

# Django
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

# wger
from wger.gallery.models import Image
from wger.measurements.models import (
    Category,
    Measurement,
)
from wger.measurements.models.category import MetricType
from wger.measurements.models.measurement import MeasurementSource


@dataclass(frozen=True)
class BodyPart:
    key: str
    name: str
    """Name of the measurement category"""


BODY_PARTS = [
    BodyPart('waist', 'Waist'),
    BodyPart('shoulders', 'Shoulders'),
    BodyPart('chest', 'Chest'),
    BodyPart('arms', 'Arms'),
    BodyPart('thighs', 'Thighs'),
]

VTAPER_CATEGORY_NAME = 'Shoulder:waist ratio'
VTAPER_TARGET = Decimal('1.6')
"""The classic aesthetic shoulder-to-waist target (the golden ratio, rounded)"""


def length_unit(user: User) -> str:
    return 'in' if user.userprofile.weight_unit == 'lb' else 'cm'


def body_categories(user: User) -> dict[str, Category]:
    """
    The user's category per body part, created if missing
    """
    categories = {}
    for part in BODY_PARTS:
        categories[part.key], _ = Category.objects.get_or_create(
            user=user,
            name=part.name,
            metric_type=MetricType.CUSTOM,
            dynamic_type=Category.DynamicType.NONE,
            defaults={'unit': length_unit(user)},
        )
    return categories


def vtaper_category(user: User, categories: dict[str, Category] | None = None) -> Category:
    """
    The calculated shoulder-to-waist category, created if missing
    """
    categories = categories or body_categories(user)
    category, _ = Category.objects.get_or_create(
        user=user,
        name=VTAPER_CATEGORY_NAME,
        dynamic_type=Category.DynamicType.SHOULDER_WAIST,
        defaults={
            'unit': '',
            'dynamic_params': {
                'shoulder_category_id': str(categories['shoulders'].pk),
                'waist_category_id': str(categories['waist'].pk),
            },
        },
    )
    return category


def local_datetime(user: User, date: datetime.date) -> datetime.datetime:
    """
    When an entry for a day is stored: now for today, else the morning of the day
    """
    tz = user.userprofile.zone_info
    if date == timezone.localdate(timezone=tz):
        return timezone.now()
    return datetime.datetime.combine(date, datetime.time(8, 0), tzinfo=tz)


def _upsert(category: Category, user: User, date: datetime.date, value: Decimal, **extra):
    """
    One entry per category and day: checking in twice on a day corrects the first one
    """
    tz = user.userprofile.zone_info
    start = datetime.datetime.combine(date, datetime.time.min, tzinfo=tz)
    existing = (
        Measurement.objects.filter(
            category=category,
            source=MeasurementSource.USER,
            date__gte=start,
            date__lt=start + datetime.timedelta(days=1),
        )
        .order_by('-date')
        .first()
    )
    if existing:
        existing.value = value
        existing.extra_data = {**existing.extra_data, **extra}
        existing.save()
        return existing
    return Measurement.objects.create(
        category=category,
        date=local_datetime(user, date),
        value=value,
        extra_data=extra,
    )


@dataclass
class CheckIn:
    date: datetime.date
    weight: Decimal | None = None
    parts: dict[str, Decimal] = field(default_factory=dict)
    photo: object = None
    notes: str = ''


def save_check_in(user: User, check_in: CheckIn) -> list[Measurement]:
    saved = []
    with transaction.atomic():
        if check_in.weight is not None:
            unit = user.userprofile.weight_unit
            category = Category.get_or_create_body_weight(user, unit=unit)
            saved.append(_upsert(category, user, check_in.date, check_in.weight, unit=unit))

        categories = body_categories(user)
        vtaper_category(user, categories)
        for key, value in check_in.parts.items():
            if value is not None:
                saved.append(_upsert(categories[key], user, check_in.date, value))

        if check_in.photo:
            Image.objects.create(
                user=user,
                date=check_in.date,
                image=check_in.photo,
                description=check_in.notes or 'Check-in',
            )
    return saved


@dataclass(frozen=True)
class Point:
    date: datetime.date
    value: Decimal


def weight_series(user: User) -> list[Point]:
    """
    Daily body weight in the profile's unit, the last entry of a day wins
    """
    unit = user.userprofile.weight_unit
    tz = user.userprofile.zone_info
    by_day = {}
    for entry in (
        Measurement.body_weight_for(user)
        .exclude(source=MeasurementSource.CALCULATED)
        .order_by('date')
    ):
        by_day[timezone.localdate(entry.date, timezone=tz)] = entry.value_in(unit)
    return [Point(d, v) for d, v in sorted(by_day.items())]


def category_series(user: User, category: Category | None) -> list[Point]:
    if category is None:
        return []
    tz = user.userprofile.zone_info
    by_day = {}
    for entry in Measurement.objects.filter(category=category).order_by('date'):
        by_day[timezone.localdate(entry.date, timezone=tz)] = entry.value
    return [Point(d, v) for d, v in sorted(by_day.items())]


def moving_average(points: list[Point], days: int = 7) -> list[Point]:
    """
    Trailing average over the last `days` calendar days, one point per entry
    """
    result = []
    for i, point in enumerate(points):
        window = [p.value for p in points[: i + 1] if (point.date - p.date).days < days]
        result.append(Point(point.date, sum(window) / len(window)))
    return result


def check_in_history(user: User, limit: int = 12) -> list[dict]:
    """
    One row per day with a measurement, newest first
    """
    rows = defaultdict(dict)
    for point in weight_series(user):
        rows[point.date]['weight'] = point.value

    categories = {
        c.name: c
        for c in Category.objects.filter(
            user=user,
            name__in=[p.name for p in BODY_PARTS] + [VTAPER_CATEGORY_NAME],
        )
    }
    for part in BODY_PARTS:
        for point in category_series(user, categories.get(part.name)):
            rows[point.date][part.key] = point.value
    for point in category_series(user, categories.get(VTAPER_CATEGORY_NAME)):
        rows[point.date]['ratio'] = point.value

    return [{'date': d, **rows[d]} for d in sorted(rows, reverse=True)[:limit]]


def steps_category(user: User) -> Category:
    """
    The user's typed steps category, shared with health-app imports
    """
    category, _ = Category.objects.get_or_create(
        user=user,
        metric_type=MetricType.STEPS,
        defaults={'name': 'Steps', 'unit': ''},
    )
    return category


def save_steps(user: User, date: datetime.date, steps: int) -> Measurement:
    with transaction.atomic():
        return _upsert(steps_category(user), user, date, Decimal(steps))


def steps_series(user: User) -> list[Point]:
    return category_series(user, steps_category(user))
