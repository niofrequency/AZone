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
Creates a user's routine, nutrition plan and measurement categories from a
ProgramSpec, using only wger's own models so everything shows up in the
regular web UI, the API and the mobile app.
"""

# Standard Library
import datetime
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
from wger.coach.programs.base import ProgramSpec
from wger.exercises.models import Exercise
from wger.manager.consts import (
    WEIGHT_UNIT_KG,
    WEIGHT_UNIT_LB,
)
from wger.manager.models import (
    Day,
    MaxRepetitionsConfig,
    RepetitionsConfig,
    RestConfig,
    RiRConfig,
    Routine,
    SetsConfig,
    Slot,
    SlotEntry,
)
from wger.measurements.models import (
    Category,
    Measurement,
)
from wger.measurements.models.category import MetricType
from wger.nutrition.models import (
    Meal,
    NutritionPlan,
)


class ProgramError(Exception):
    """Raised when a program cannot be applied to a user"""


@dataclass
class SeedResult:
    routine: Routine
    plan: NutritionPlan
    categories: list[Category] = field(default_factory=list)
    body_weight: Measurement | None = None


def seed_program(
    user: User,
    program: ProgramSpec,
    *,
    start: datetime.date | None = None,
    current_weight: Decimal | None = None,
    weight_unit: str = 'lb',
    replace: bool = False,
) -> SeedResult:
    """
    Applies a program to a user. Everything happens in one transaction, so a
    failure leaves the user's data untouched.

    :param start: first day of the routine, defaults to today
    :param current_weight: if given, logged as today's body weight
    :param weight_unit: 'lb' or 'kg', used for the profile and all exercises
    :param replace: recreate the routine of a previous run of this program and
        update its nutrition plan in place. Workout and nutrition logs are kept
    """
    if weight_unit not in ('lb', 'kg'):
        raise ProgramError(f'Unknown weight unit "{weight_unit}", use "lb" or "kg"')

    start = start or timezone.localdate()
    exercises = _resolve_exercises(program)

    with transaction.atomic():
        existing_routines = Routine.objects.filter(user=user, name=program.name)
        existing_plans = NutritionPlan.objects.filter(
            user=user,
            description=program.nutrition.description,
        )
        if (existing_routines.exists() or existing_plans.exists()) and not replace:
            raise ProgramError(
                f'User "{user.username}" already has the "{program.name}" program. '
                f'Use --replace to recreate the routine and update the nutrition goals.'
            )
        # Workout logs survive this, their routine reference is set to NULL
        existing_routines.delete()

        profile = user.userprofile
        if profile.weight_unit != weight_unit:
            profile.weight_unit = weight_unit
            profile.save()

        result = SeedResult(
            routine=_create_routine(user, program, exercises, start, weight_unit),
            plan=_create_or_update_nutrition_plan(user, program, start, existing_plans.first()),
            categories=_create_measurement_categories(user, program),
        )
        if current_weight is not None:
            result.body_weight = _log_body_weight(user, current_weight, weight_unit)

    return result


def _resolve_exercises(program: ProgramSpec) -> dict[str, Exercise]:
    uuids = [e.uuid for day in program.days for e in day.exercises]
    found = {str(e.uuid): e for e in Exercise.objects.filter(uuid__in=uuids)}

    missing = [e.name for day in program.days for e in day.exercises if e.uuid not in found]
    if missing:
        raise ProgramError(
            'These exercises are not in the database: '
            + ', '.join(missing)
            + '. Load the exercise data first (wger bootstrap or wger load-fixtures).'
        )
    return found


def _create_routine(
    user: User,
    program: ProgramSpec,
    exercises: dict[str, Exercise],
    start: datetime.date,
    weight_unit: str,
) -> Routine:
    duration = min(program.weeks * 7, Routine.MAX_DURATION_DAYS) - 1
    routine = Routine.objects.create(
        user=user,
        name=program.name,
        description=program.description,
        start=start,
        end=start + datetime.timedelta(days=duration),
    )
    weight_unit_id = WEIGHT_UNIT_LB if weight_unit == 'lb' else WEIGHT_UNIT_KG

    order = 1
    for day_spec in program.days:
        day = Day.objects.create(
            routine=routine,
            order=order,
            name=day_spec.name,
            description=day_spec.description,
            # Missed a session? The day waits for you instead of being skipped,
            # which keeps the progression of every exercise in order
            need_logs_to_advance=True,
        )
        order += 1

        for slot_order, spec in enumerate(day_spec.exercises, start=1):
            slot = Slot.objects.create(day=day, order=slot_order, comment=spec.notes)
            entry = SlotEntry.objects.create(
                slot=slot,
                exercise=exercises[spec.uuid],
                order=1,
                weight_unit_id=weight_unit_id,
            )
            for config_class, value in (
                (SetsConfig, spec.sets),
                (RepetitionsConfig, spec.reps_min),
                (MaxRepetitionsConfig, spec.reps_max),
                (RiRConfig, spec.rir),
                (RestConfig, spec.rest),
            ):
                config_class.objects.create(slot_entry=entry, iteration=1, value=value)

    for _ in range(program.rest_days_after_cycle):
        Day.objects.create(routine=routine, order=order, name='Rest', is_rest=True)
        order += 1

    return routine


def _create_or_update_nutrition_plan(
    user: User,
    program: ProgramSpec,
    start: datetime.date,
    plan: NutritionPlan | None,
) -> NutritionPlan:
    """
    An existing plan is updated rather than deleted, deleting it would also
    delete the food diary logged against it
    """
    spec = program.nutrition
    plan = plan or NutritionPlan(user=user, description=spec.description, start=start)
    plan.has_goal_calories = True
    plan.goal_energy = spec.energy
    plan.goal_protein = spec.protein
    plan.goal_carbohydrates = spec.carbohydrates
    plan.goal_fat = spec.fat
    plan.goal_fiber = spec.fiber
    plan.save()

    existing_meals = set(plan.meal_set.values_list('name', flat=True))
    for order, meal in enumerate(spec.meals, start=1):
        if meal.name not in existing_meals:
            Meal.objects.create(plan=plan, order=order, name=meal.name, time=meal.time)

    return plan


def _create_measurement_categories(user: User, program: ProgramSpec) -> list[Category]:
    categories = []
    for spec in program.measurements:
        if spec.metric_type == MetricType.CUSTOM:
            category, _ = Category.objects.get_or_create(
                user=user,
                name=spec.name,
                metric_type=MetricType.CUSTOM,
                defaults={'unit': spec.unit},
            )
        else:
            # Typed categories are unique per user, reuse one the user may already have
            category, _ = Category.objects.get_or_create(
                user=user,
                metric_type=spec.metric_type,
                defaults={'name': spec.name, 'unit': spec.unit},
            )
        categories.append(category)
    return categories


def _log_body_weight(user: User, value: Decimal, unit: str) -> Measurement:
    category = Category.get_or_create_body_weight(user, unit=unit)
    return Measurement.objects.create(
        category=category,
        value=value,
        extra_data={'unit': unit},
    )
