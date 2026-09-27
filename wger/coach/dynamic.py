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
Calculated measurement types of the coach app. They plug into wger's dynamic
measurement engine (wger/measurements/dynamic), so the values are recomputed
whenever a source measurement changes and show up in every measurement view.
"""

# Standard Library
import datetime
from decimal import Decimal

# Django
from django.core.exceptions import ValidationError as DjangoValidationError

# wger
from wger.measurements.dynamic.base import (
    Dependency,
    DesiredRow,
    DynamicMeasurementType,
    register,
)
from wger.measurements.dynamic.types import LENGTH_UNITS
from wger.measurements.models import (
    Category,
    Measurement,
)
from wger.measurements.models.measurement import MeasurementSource


MAX_PAIRING_DAYS = 3
"""How far apart a shoulder and a waist measurement may be to form a ratio"""


def length_factor(unit: str) -> Decimal | None:
    return LENGTH_UNITS.get((unit or '').strip().lower().rstrip('.'))


@register
class ShoulderWaistRatio(DynamicMeasurementType):
    """
    Shoulder circumference divided by waist circumference, the "V-taper" or
    Adonis index. One entry per shoulder measurement, paired with the closest
    waist measurement at most MAX_PAIRING_DAYS away. ~1.6 is the classic
    aesthetic target.
    """

    slug = Category.DynamicType.SHOULDER_WAIST
    label = 'Shoulder-to-waist ratio'
    params_schema = {
        'type': 'object',
        'properties': {
            'shoulder_category_id': {'type': 'string'},
            'waist_category_id': {'type': 'string'},
        },
        'required': ['shoulder_category_id', 'waist_category_id'],
        'additionalProperties': False,
    }
    depends_on = [
        Dependency(
            Measurement,
            user_id=lambda entry: entry.category.user_id,
            when=lambda entry: entry.category.dynamic_type == Category.DynamicType.NONE,
        ),
    ]

    @staticmethod
    def _category(user_id, pk) -> Category | None:
        try:
            return Category.objects.get(pk=pk, user_id=user_id)
        except (Category.DoesNotExist, DjangoValidationError, ValueError, TypeError):
            return None

    def validate_params(self, user_id, params):
        for key in ('shoulder_category_id', 'waist_category_id'):
            source = self._category(user_id, params.get(key))
            if source is None:
                raise ValueError('The source category does not exist')
            if source.dynamic_type != Category.DynamicType.NONE:
                raise ValueError('A calculated category cannot be the source of another one')
            if length_factor(source.unit) is None:
                raise ValueError('The source category has to be measured in a length unit')

    @staticmethod
    def _entries(category: Category) -> list[tuple[Measurement, Decimal]]:
        """
        The entries of a category with their value in centimeters
        """
        rows = []
        for entry in Measurement.objects.filter(category=category).exclude(
            source=MeasurementSource.CALCULATED
        ):
            factor = length_factor(entry.unit)
            if factor is not None and entry.value > 0:
                rows.append((entry, entry.value * factor))
        return rows

    def compute(self, category: Category) -> list[DesiredRow]:
        params = category.dynamic_params or {}
        shoulder = self._category(category.user_id, params.get('shoulder_category_id'))
        waist = self._category(category.user_id, params.get('waist_category_id'))
        if shoulder is None or waist is None or category.pk in (shoulder.pk, waist.pk):
            return []

        waists = self._entries(waist)
        max_distance = datetime.timedelta(days=MAX_PAIRING_DAYS)

        rows = []
        for entry, shoulder_cm in self._entries(shoulder):
            closest = min(
                waists,
                key=lambda w: abs(w[0].date - entry.date),
                default=None,
            )
            if closest is None or abs(closest[0].date - entry.date) > max_distance:
                continue
            rows.append(
                DesiredRow(
                    external_id=entry.pk,
                    date=entry.date,
                    value=round(shoulder_cm / closest[1], 2),
                )
            )
        return rows
