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

# Standard Library
import datetime
from decimal import Decimal

# Django
from django.contrib.auth.models import User
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models


class FocusArea(models.TextChoices):
    """
    Body parts a user wants to prioritise. The rules engine gives these more
    weekly volume
    """

    UPPER_CHEST = 'upper_chest', 'Upper chest'
    LATS = 'lats', 'Lats (V-taper)'
    SIDE_DELTS = 'side_delts', 'Side delts (shoulder width)'
    REAR_DELTS = 'rear_delts', 'Rear delts / upper back'
    ARMS = 'arms', 'Arms'
    QUADS = 'quads', 'Quads'
    HAMSTRINGS = 'hamstrings', 'Hamstrings'
    GLUTES = 'glutes', 'Glutes'
    CALVES = 'calves', 'Calves'
    ABS = 'abs', 'Abs / midsection'


class CoachGoal(models.Model):
    """
    What a user is working towards. Weights are stored in `weight_unit`
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='coach_goal')

    weight_unit = models.CharField(
        max_length=2,
        choices=[('lb', 'lb'), ('kg', 'kg')],
        default='lb',
    )

    start_date = models.DateField(default=datetime.date.today)

    start_weight = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(20), MaxValueValidator(800)],
        help_text='Leave empty to use your first weigh-in',
    )

    target_weight = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        validators=[MinValueValidator(20), MaxValueValidator(800)],
    )

    target_date = models.DateField()

    rate_min_per_week = models.DecimalField(
        'Slowest weekly change',
        max_digits=3,
        decimal_places=1,
        default=Decimal('1.0'),
        validators=[MinValueValidator(0)],
        help_text='Weight lost (or gained) per week that still counts as on track',
    )

    rate_max_per_week = models.DecimalField(
        'Fastest weekly change',
        max_digits=3,
        decimal_places=1,
        default=Decimal('1.5'),
        validators=[MinValueValidator(0)],
        help_text='Faster than this and you risk losing muscle',
    )

    protein_target = models.PositiveIntegerField(
        'Daily protein (g)',
        default=165,
        validators=[MaxValueValidator(500)],
    )

    step_target = models.PositiveIntegerField(
        'Daily steps',
        default=10000,
        validators=[MaxValueValidator(100000)],
    )

    focus = models.JSONField(
        default=list,
        blank=True,
        help_text='Body parts to prioritise, see FocusArea',
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username}: {self.target_weight} {self.weight_unit}'

    def get_owner_object(self):
        return self

    @property
    def is_cut(self) -> bool:
        return self.start_weight is None or self.target_weight <= self.start_weight

    @property
    def weeks(self) -> Decimal:
        return Decimal((self.target_date - self.start_date).days) / 7

    def planned_weight(self, date: datetime.date) -> Decimal | None:
        """
        Where the straight line from start to target puts the weight on a date
        """
        if self.start_weight is None:
            return None
        total_days = (self.target_date - self.start_date).days
        if total_days <= 0:
            return self.target_weight
        progress = min(max((date - self.start_date).days / total_days, 0), 1)
        return self.start_weight + (self.target_weight - self.start_weight) * Decimal(progress)
