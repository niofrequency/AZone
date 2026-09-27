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


MIN_LOGGED_DAYS = 3
PROTEIN_TOLERANCE = 15
CALORIE_TOLERANCE = 200


def nutrition(ctx: RuleContext) -> list[Finding]:
    """
    Average protein and calories of the last 7 fully logged days (today is
    still in progress, so it doesn't count)
    """
    goal = ctx.goal
    since = ctx.today - datetime.timedelta(days=7)
    days = {d: v for d, v in ctx.nutrition_by_day.items() if since <= d < ctx.today}
    if len(days) < MIN_LOGGED_DAYS:
        if goal is None:
            return []
        return [
            Finding(
                key='nutrition:need_data',
                severity=Severity.INFO,
                title='Log your meals to get nutrition feedback',
                body=(
                    f'Log at least {MIN_LOGGED_DAYS} days a week under Nutrition so the coach can '
                    f'check your protein ({goal.protein_target} g) and calories.'
                ),
            )
        ]

    findings = []
    protein = sum(Decimal(v.protein) for v in days.values()) / len(days)
    energy = sum(Decimal(v.energy) for v in days.values()) / len(days)

    target = goal.protein_target if goal else (ctx.plan.goal_protein if ctx.plan else None)
    if target:
        if protein < target - PROTEIN_TOLERANCE:
            findings.append(
                Finding(
                    key='nutrition:protein_low',
                    severity=Severity.ADJUST,
                    title=f'Protein is short: {protein:.0f} g of {target} g a day',
                    body=(
                        f'About {target - protein:.0f} g a day missing over the last {len(days)} '
                        'logged days. Protein keeps muscle on a cut. Easy fixes: a shake or Greek '
                        'yogurt pre-workout, or an extra 2 egg whites at breakfast.'
                    ),
                )
            )
        else:
            findings.append(
                Finding(
                    key='nutrition:protein_ok',
                    severity=Severity.GOOD,
                    title=f'Protein on target: {protein:.0f} g a day',
                    body=f'Averaged over the last {len(days)} logged days (goal {target} g).',
                )
            )

    energy_goal = ctx.plan.goal_energy if ctx.plan else None
    if energy_goal and energy > energy_goal + CALORIE_TOLERANCE:
        findings.append(
            Finding(
                key='nutrition:calories_high',
                severity=Severity.INFO,
                title=f'Eating about {energy - energy_goal:.0f} kcal over your goal',
                body=(
                    f'{energy:.0f} kcal a day on average vs. {energy_goal} kcal planned. Check '
                    'sauces, oils and drinks; they add up fast.'
                ),
            )
        )
    return findings
