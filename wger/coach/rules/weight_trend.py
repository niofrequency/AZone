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

# wger
from wger.coach.models import Severity
from wger.coach.rules.base import (
    Finding,
    RuleContext,
)


CALORIE_STEP = 150
MIN_WEIGH_INS_PER_WEEK = 3


def fmt(value: Decimal) -> str:
    return f'{abs(value):.1f}'


def weight_trend(ctx: RuleContext) -> list[Finding]:
    """
    Compares this week's average weight with last week's and checks the pace
    against the goal. Averages over a week filter out water and salt swings
    """
    goal = ctx.goal
    if goal is None:
        return []
    unit = ctx.weight_unit

    current, current_count = ctx.average_weight(ctx.today)
    previous, previous_count = ctx.average_weight(ctx.today - datetime.timedelta(days=7))
    if current_count < MIN_WEIGH_INS_PER_WEEK or previous_count < MIN_WEIGH_INS_PER_WEEK:
        return [
            Finding(
                key='weight_trend:need_data',
                severity=Severity.INFO,
                title='Weigh in daily to see your trend',
                body=(
                    f'The coach needs at least {MIN_WEIGH_INS_PER_WEEK} weigh-ins in each of the '
                    'last two weeks to calculate your weekly pace.'
                ),
            )
        ]

    direction = -1 if goal.is_cut else 1
    progress = (current - previous) * direction
    """Positive means moving towards the goal"""
    verb = 'losing' if goal.is_cut else 'gaining'

    reached = current <= goal.target_weight if goal.is_cut else current >= goal.target_weight
    if reached:
        return [
            Finding(
                key='weight_trend:reached',
                severity=Severity.GOOD,
                title=f'Goal reached: {current:.1f} {unit}',
                body='Time to set a new goal, or switch to maintenance calories.',
            )
        ]

    plan = ctx.plan
    has_calories = plan is not None and plan.goal_energy

    def calorie_action(delta: int) -> dict | None:
        if not has_calories:
            return None
        return {'type': 'calories', 'plan': str(plan.pk), 'delta': delta}

    too_slow = progress < goal.rate_min_per_week / 2
    too_fast = progress > goal.rate_max_per_week + Decimal('0.5')

    target_pace = f'{goal.rate_min_per_week}–{goal.rate_max_per_week} {unit}/week'

    def calorie_label(delta: int) -> str:
        return f'{"Raise" if delta > 0 else "Lower"} calorie goal by {abs(delta)} kcal'

    # direction is -1 on a cut: too slow means eating less, too fast eating more
    if too_slow:
        delta = CALORIE_STEP * direction
        if delta < 0:
            advice = (
                f'Cut about {CALORIE_STEP} kcal a day (e.g. a smaller carb portion at dinner) '
                'or add ~2,000 steps.'
            )
        else:
            advice = f'Add about {CALORIE_STEP} kcal a day.'
        return [
            Finding(
                key='weight_trend:slow',
                severity=Severity.ADJUST,
                title=f'Progress has slowed to {fmt(progress)} {unit}/week',
                body=(
                    f'Your 7-day average went from {previous:.1f} to {current:.1f} {unit}. '
                    f'The target is {target_pace}. {advice}'
                ),
                action=calorie_action(delta),
                action_label=calorie_label(delta),
            )
        ]

    if too_fast:
        delta = -CALORIE_STEP * direction
        if goal.is_cut:
            advice = (
                f'Above {goal.rate_max_per_week} {unit}/week you risk losing muscle and '
                f'strength. Add about {CALORIE_STEP} kcal a day, ideally carbs around workouts.'
            )
        else:
            advice = f'Faster gains are mostly fat. Cut about {CALORIE_STEP} kcal a day.'
        return [
            Finding(
                key='weight_trend:fast',
                severity=Severity.WARNING,
                title=f'{verb.capitalize()} {fmt(progress)} {unit}/week, faster than planned',
                body=advice,
                action=calorie_action(delta),
                action_label=calorie_label(delta),
            )
        ]

    to_go = abs(current - goal.target_weight)
    weeks_needed = to_go / progress if progress > 0 else None
    eta = ''
    if weeks_needed is not None:
        eta_date = ctx.today + datetime.timedelta(weeks=float(weeks_needed))
        eta = f' At this pace you reach {goal.target_weight:.0f} {unit} around {eta_date:%b %-d}.'

    if progress < goal.rate_min_per_week:
        return [
            Finding(
                key='weight_trend:slightly_slow',
                severity=Severity.INFO,
                title=f'{verb.capitalize()} {fmt(progress)} {unit}/week, a little slow',
                body=(
                    f'The target is {target_pace}. '
                    'Give it another week before changing anything; tighten up weekend meals and '
                    f'hit your step goal.{eta}'
                ),
            )
        ]

    return [
        Finding(
            key='weight_trend:on_track',
            severity=Severity.GOOD,
            title=f'On track: {verb} {fmt(progress)} {unit}/week',
            body=f'7-day average {current:.1f} {unit}, {to_go:.1f} {unit} to go.{eta}',
        )
    ]
