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


MIN_DAYS = 3
STEPS_FLOOR = 8000
CARDIO_WEEKLY_MINUTES = 150
"""About 30 minutes on 5 days, the low end of the plan's 30-45 min walks"""


def activity(ctx: RuleContext) -> list[Finding]:
    """
    Daily steps and weekly low-intensity cardio (NEAT), the easiest lever on
    a cut besides food
    """
    findings = []
    since = ctx.today - datetime.timedelta(days=6)
    target = ctx.goal.step_target if ctx.goal else 10000
    floor = min(STEPS_FLOOR, target)

    days = [p for p in ctx.steps if since <= p.date <= ctx.today]
    if len(days) >= MIN_DAYS:
        average = sum(p.value for p in days) / len(days)
        if average < floor:
            findings.append(
                Finding(
                    key='activity:steps_low',
                    severity=Severity.ADJUST,
                    title=f'Averaging {average:,.0f} steps a day',
                    body=(
                        f'Aim for at least {floor:,} (ideally {target:,}). A 10-minute walk after '
                        'each meal adds about 3,000 steps.'
                    ),
                )
            )
        else:
            findings.append(
                Finding(
                    key='activity:steps_ok',
                    severity=Severity.GOOD,
                    title=f'Averaging {average:,.0f} steps a day',
                    body=f'Over the last {len(days)} logged days (goal {target:,}).',
                )
            )

    sessions = ctx.cardio_week
    minutes = sum(s.duration for s in sessions)
    if minutes >= CARDIO_WEEKLY_MINUTES:
        findings.append(
            Finding(
                key='activity:cardio_ok',
                severity=Severity.GOOD,
                title=f'{minutes} minutes of cardio this week',
                body=f'{len(sessions)} sessions in the last 7 days.',
            )
        )
    elif ctx.goal is not None and ctx.goal.is_cut:
        findings.append(
            Finding(
                key='activity:cardio_low',
                severity=Severity.INFO,
                title=f'{minutes} minutes of cardio in the last 7 days',
                body=(
                    'The plan calls for a 30-45 minute incline walk most mornings (10-12% incline, '
                    '3.0-3.5 mph) or 15-20 minutes after lifting. Log them under Cardio & steps.'
                ),
            )
        )
    return findings


def weekly_cardio_minutes(ctx: RuleContext) -> int:
    return sum(s.duration for s in ctx.cardio_week)


def average_steps(ctx: RuleContext) -> Decimal | None:
    since = ctx.today - datetime.timedelta(days=6)
    days = [p.value for p in ctx.steps if since <= p.date <= ctx.today]
    return sum(days) / len(days) if days else None
