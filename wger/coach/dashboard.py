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
The numbers on the coach dashboard
"""

# Standard Library
import datetime
from dataclasses import dataclass
from decimal import Decimal

# wger
from wger.coach.rules.base import RuleContext


@dataclass
class Tile:
    label: str
    value: str
    detail: str = ''
    tone: str = ''
    """'good', 'warning' or '' - colours the detail line, always with words"""


@dataclass
class Progress:
    exercise: str
    change: str
    current: str
    improved: bool


def tiles(ctx: RuleContext) -> list[Tile]:
    goal = ctx.goal
    unit = ctx.weight_unit
    result = []

    current, count = ctx.average_weight(ctx.today)
    if current is not None:
        detail = ''
        if goal is not None and goal.start_weight is not None:
            change = current - goal.start_weight
            detail = f'{change:+.1f} {unit} since start'
        result.append(Tile('7-day average weight', f'{current:.1f} {unit}', detail))

        previous, previous_count = ctx.average_weight(ctx.today - datetime.timedelta(days=7))
        if previous is not None and count >= 3 and previous_count >= 3:
            weekly = current - previous
            tone, pace = '', ''
            if goal is not None:
                progress = -weekly if goal.is_cut else weekly
                if progress < goal.rate_min_per_week:
                    tone, pace = 'warning', 'slower than'
                elif progress > goal.rate_max_per_week:
                    tone, pace = 'warning', 'faster than'
                else:
                    tone, pace = 'good', 'on'
            result.append(
                Tile(
                    'Weekly pace',
                    f'{weekly:+.1f} {unit}',
                    (f'{pace} target of {goal.rate_min_per_week}–{goal.rate_max_per_week}')
                    if goal
                    else '',
                    tone,
                )
            )

    if goal is not None:
        days_left = (goal.target_date - ctx.today).days
        to_go = f'{abs(current - goal.target_weight):.1f} {unit}' if current is not None else '–'
        result.append(
            Tile(
                'To go',
                to_go,
                f'{max(days_left, 0) // 7} weeks, {max(days_left, 0) % 7} days left',
            )
        )

    if ctx.ratio_series:
        result.append(Tile('Shoulder:waist', f'{ctx.ratio_series[-1].value:.2f}', 'target 1.60'))

    today = ctx.nutrition_by_day.get(ctx.today)
    plan = ctx.plan
    protein_goal = goal.protein_target if goal else (plan.goal_protein if plan else None)
    if protein_goal:
        protein = Decimal(today.protein) if today else Decimal(0)
        result.append(Tile('Protein today', f'{protein:.0f} g', f'of {protein_goal} g'))
    if plan is not None and plan.goal_energy:
        energy = Decimal(today.energy) if today else Decimal(0)
        result.append(Tile('Calories today', f'{energy:,.0f}', f'of {plan.goal_energy:,} kcal'))
    return result


def next_workout(ctx: RuleContext):
    """
    Today's or the next training day of the routine, as (date, day)
    """
    if ctx.routine is None:
        return None
    for item in ctx.routine.date_sequence:
        if item.date >= ctx.today and item.day is not None and not item.day.is_rest:
            return item
    return None


def recent_progress(ctx: RuleContext) -> list[Progress]:
    """
    The latest session of each exercise compared with the one before
    """
    unit = ctx.weight_unit
    result = []
    for entry in ctx.entries:
        sessions = ctx.sessions.get(entry.pk, [])
        if len(sessions) < 2:
            continue
        before, last = sessions[-2], sessions[-1]
        weight_change = Decimal(last.weight or 0) - Decimal(before.weight or 0)
        reps_change = last.total_reps - before.total_reps
        if weight_change:
            change = f'{float(weight_change):+g} {unit}'
            improved = weight_change > 0
        elif reps_change:
            change = f'{reps_change:+d} reps'
            improved = reps_change > 0
        else:
            change = 'same'
            improved = False
        weight = f' @ {float(last.weight):g} {unit}' if last.weight else ''
        result.append(
            Progress(
                exercise=ctx.exercise_name(entry),
                change=change,
                current=f'{last.sets} sets, {last.total_reps} reps{weight}',
                improved=improved,
            )
        )
    return result
