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
What "Apply" does for each kind of recommendation action
"""

# Django
from django.db import transaction
from django.utils import timezone

# wger
from wger.coach.models import (
    Recommendation,
    RecommendationStatus,
)
from wger.coach.rules.base import exercise_name
from wger.manager.models import (
    SetsConfig,
    SlotEntry,
    WorkoutLog,
)
from wger.manager.models.slot import Slot
from wger.nutrition.models import NutritionPlan


class ActionError(Exception):
    pass


MIN_CARBS = 50
MIN_CALORIES = 1200


def apply_calories(user, action: dict) -> str:
    try:
        plan = NutritionPlan.objects.get(pk=action['plan'], user=user)
    except (NutritionPlan.DoesNotExist, KeyError, ValueError):
        raise ActionError('The nutrition plan does not exist anymore')
    if not plan.goal_energy:
        raise ActionError('The nutrition plan has no calorie goal')

    delta = int(action['delta'])
    plan.goal_energy = max(plan.goal_energy + delta, MIN_CALORIES)
    if plan.goal_carbohydrates:
        # The change comes out of (or goes into) carbs, protein stays put
        plan.goal_carbohydrates = max(plan.goal_carbohydrates + round(delta / 4), MIN_CARBS)
    plan.save()
    return f'Calorie goal is now {plan.goal_energy} kcal.'


def apply_add_set(user, action: dict) -> str:
    try:
        entry = SlotEntry.objects.select_related('slot__day__routine').get(
            pk=action['slot_entry'],
            slot__day__routine__user=user,
        )
    except (SlotEntry.DoesNotExist, KeyError, ValueError):
        raise ActionError('The exercise is not in your routine anymore')

    # The change starts with the next session of the exercise
    last = (
        WorkoutLog.objects.filter(user=user, slot_entry=entry)
        .order_by('-iteration')
        .values_list('iteration', flat=True)
        .first()
    )
    iteration = (last or 0) + 1
    sets = (entry.get_config_data(iteration).sets or 0) + 1
    SetsConfig.objects.update_or_create(
        slot_entry=entry,
        iteration=iteration,
        defaults={'value': min(sets, Slot.MAX_SETS)},
    )
    return f'{exercise_name(entry.exercise)} now has {sets} sets.'


ACTIONS = {
    'calories': apply_calories,
    'add_set': apply_add_set,
}


def apply(recommendation: Recommendation) -> str:
    if not recommendation.can_apply:
        raise ActionError('This recommendation cannot be applied')
    handler = ACTIONS.get(recommendation.action.get('type'))
    if handler is None:
        raise ActionError('Unknown action')

    with transaction.atomic():
        message = handler(recommendation.user, recommendation.action)
        recommendation.status = RecommendationStatus.APPLIED
        recommendation.resolved = timezone.now()
        recommendation.save()
    return message


def dismiss(recommendation: Recommendation) -> None:
    recommendation.status = RecommendationStatus.DISMISSED
    recommendation.resolved = timezone.now()
    recommendation.save()
