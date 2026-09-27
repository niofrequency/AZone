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
Shared pieces of the coach rules: what a rule returns, and the context with
the user's data every rule reads from. Data is loaded lazily and only once
per run.
"""

# Standard Library
import datetime
from collections import defaultdict
from dataclasses import (
    dataclass,
    field,
)
from decimal import Decimal
from functools import cached_property

# Django
from django.contrib.auth.models import User
from django.utils import timezone

# wger
from wger.coach.body import (
    Point,
    body_categories,
    category_series,
    vtaper_category,
    weight_series,
)
from wger.coach.models import CoachGoal
from wger.manager.models import (
    Routine,
    SlotEntry,
    WorkoutLog,
)
from wger.nutrition.helpers import NutritionalValues
from wger.nutrition.models import NutritionPlan


@dataclass
class Finding:
    key: str
    """Identifies the finding across runs, e.g. 'weight_trend:slow'"""

    severity: str
    title: str
    body: str = ''
    action: dict | None = None
    action_label: str = ''
    rule: str = ''


FOCUS_MUSCLES: dict[str, set[int]] = {
    # Keys of FocusArea -> ids of wger's muscles (wger/exercises/fixtures/muscles.json)
    'upper_chest': {4},
    'lats': {12},
    'side_delts': {2},
    'rear_delts': {9},
    'arms': {1, 5, 13},
    'quads': {10},
    'hamstrings': {11},
    'glutes': {8},
    'calves': {7, 15},
    'abs': {6, 14},
}

PUSH_MUSCLES = {4, 5}
"""Chest and triceps"""

PULL_MUSCLES = {12, 9, 1}
"""Lats, trapezius / upper back and biceps"""


@dataclass
class Session:
    """One logged session of one exercise"""

    iteration: int
    date: datetime.date
    weight: Decimal | None
    total_reps: int
    sets: int


@dataclass
class RuleContext:
    user: User
    today: datetime.date = field(default=None)

    def __post_init__(self):
        if self.today is None:
            self.today = timezone.localdate(timezone=self.user.userprofile.zone_info)

    @cached_property
    def goal(self) -> CoachGoal | None:
        return CoachGoal.objects.filter(user=self.user).first()

    @cached_property
    def weight_unit(self) -> str:
        return self.goal.weight_unit if self.goal else self.user.userprofile.weight_unit

    @cached_property
    def weights(self) -> list[Point]:
        return weight_series(self.user)

    def average_weight(self, end: datetime.date, days: int = 7) -> tuple[Decimal | None, int]:
        """
        Average of the weigh-ins in the `days` days up to and including `end`
        """
        start = end - datetime.timedelta(days=days - 1)
        values = [p.value for p in self.weights if start <= p.date <= end]
        return (sum(values) / len(values), len(values)) if values else (None, 0)

    @cached_property
    def body_categories(self):
        return body_categories(self.user)

    def body_series(self, key: str) -> list[Point]:
        return category_series(self.user, self.body_categories[key])

    @cached_property
    def ratio_series(self) -> list[Point]:
        return category_series(self.user, vtaper_category(self.user, self.body_categories))

    @cached_property
    def plan(self) -> NutritionPlan | None:
        """
        The nutrition plan the user logs against: the newest one with goals
        """
        plans = NutritionPlan.objects.filter(user=self.user).order_by('-start', '-creation_date')
        return plans.filter(has_goal_calories=True).first() or plans.first()

    @cached_property
    def nutrition_by_day(self) -> dict[datetime.date, NutritionalValues]:
        """
        Logged nutrition of the last 14 days, all plans
        """
        tz = self.user.userprofile.zone_info
        since = self.today - datetime.timedelta(days=14)
        totals = defaultdict(NutritionalValues)
        for plan in NutritionPlan.objects.filter(user=self.user):
            for item in plan.logitem_set.filter(
                datetime__date__gte=since - datetime.timedelta(days=1)
            ).select_related('ingredient', 'weight_unit'):
                day = timezone.localdate(item.datetime, timezone=tz)
                if day >= since:
                    totals[day] = totals[day] + item.get_nutritional_values()
        return dict(totals)

    @cached_property
    def routine(self) -> Routine | None:
        """
        The routine running today, or the newest one
        """
        routines = Routine.objects.filter(user=self.user, is_template=False)
        return (
            routines.filter(start__lte=self.today, end__gte=self.today).order_by('-start').first()
            or routines.order_by('-start').first()
        )

    @cached_property
    def entries(self) -> list[SlotEntry]:
        if self.routine is None:
            return []
        return list(
            SlotEntry.objects.filter(slot__day__routine=self.routine, slot__day__is_rest=False)
            .select_related('exercise', 'slot__day')
            .prefetch_related('exercise__muscles', 'exercise__translations')
            .order_by('slot__day__order', 'slot__order', 'order')
        )

    @cached_property
    def cycle_days(self) -> int:
        return self.routine.days.count() if self.routine else 0

    @cached_property
    def sessions(self) -> dict[int, list[Session]]:
        """
        Logged sessions per slot entry, oldest first
        """
        logs = WorkoutLog.objects.filter(
            user=self.user,
            slot_entry__in=[e.pk for e in self.entries],
            repetitions__isnull=False,
        ).order_by('date')
        grouped = defaultdict(lambda: defaultdict(list))
        for log in logs:
            grouped[log.slot_entry_id][log.iteration].append(log)

        result = {}
        for entry_id, by_iteration in grouped.items():
            sessions = []
            for iteration, entry_logs in sorted(by_iteration.items()):
                weights = [log.weight for log in entry_logs if log.weight is not None]
                sessions.append(
                    Session(
                        iteration=iteration,
                        date=timezone.localdate(entry_logs[-1].date),
                        weight=max(weights, key=weights.count) if weights else None,
                        total_reps=int(sum(log.repetitions for log in entry_logs)),
                        sets=len(entry_logs),
                    )
                )
            result[entry_id] = sessions
        return result

    def next_iteration(self, entry: SlotEntry) -> int:
        sessions = self.sessions.get(entry.pk, [])
        return sessions[-1].iteration + 1 if sessions else 1

    def planned_sets(self, entry: SlotEntry) -> int:
        return entry.get_config_data(self.next_iteration(entry)).sets or 0

    def weekly_sets(self, entry: SlotEntry) -> Decimal:
        """
        Sets per week of an entry: its day comes around every `cycle_days` days
        """
        if not self.cycle_days:
            return Decimal(0)
        days_per_week = 7 if self.routine.fit_in_week else Decimal(7) / self.cycle_days
        return self.planned_sets(entry) * Decimal(days_per_week)

    def muscles(self, entry: SlotEntry) -> set[int]:
        return {m.pk for m in entry.exercise.muscles.all()}

    def exercise_name(self, entry: SlotEntry) -> str:
        return exercise_name(entry.exercise)


def exercise_name(exercise) -> str:
    translation = exercise.get_translation()
    return translation.name if translation else f'Exercise {exercise.pk}'
