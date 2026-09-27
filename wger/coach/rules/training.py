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
from decimal import Decimal

# wger
from wger.coach.models import (
    FocusArea,
    Severity,
)
from wger.coach.rules.base import (
    FOCUS_MUSCLES,
    PULL_MUSCLES,
    PUSH_MUSCLES,
    Finding,
    RuleContext,
)


FOCUS_MIN_SETS = 10
"""Weekly hard sets below which a focus muscle gets more volume"""

MAX_SETS_PER_EXERCISE = 6
PUSH_PULL_MAX = Decimal('1.3')
STALL_SESSIONS = 3


def add_set_action(entry) -> dict:
    return {'type': 'add_set', 'slot_entry': entry.pk}


def volume_finding(ctx: RuleContext, area: str, reason: str = '') -> Finding | None:
    """
    +1 set on the most isolated exercise that trains `area`, if that area
    gets fewer than FOCUS_MIN_SETS sets a week
    """
    muscles = FOCUS_MUSCLES[area]
    entries = [e for e in ctx.entries if ctx.muscles(e) & muscles]
    label = FocusArea(area).label
    if not entries and area == 'abs':
        return Finding(
            key='volume:abs',
            severity=Severity.INFO,
            title='Abs come through with fat loss',
            body=(
                'Your routine has no direct ab work, which is fine: the waist measurement tracks '
                'what matters. For extra definition add 2–3 sets of hanging leg raises or cable '
                'crunches to Lower B.'
            ),
        )
    if not entries:
        return Finding(
            key=f'volume:{area}',
            severity=Severity.INFO,
            title=f'No exercise in your routine trains {label.lower()}',
            body=f'{reason} Add one to your routine to work on this focus area.'.strip(),
        )

    weekly = sum(ctx.weekly_sets(e) for e in entries)
    if weekly >= FOCUS_MIN_SETS:
        return None

    candidates = [e for e in entries if ctx.planned_sets(e) < MAX_SETS_PER_EXERCISE]
    if not candidates:
        return None
    entry = min(candidates, key=lambda e: (len(ctx.muscles(e)), -e.slot.order))
    name = ctx.exercise_name(entry)
    return Finding(
        key=f'volume:{area}',
        severity=Severity.ADJUST,
        title=f'{label}: about {weekly:.0f} sets a week',
        body=(
            f'{reason} A focus muscle grows best with {FOCUS_MIN_SETS}–20 hard sets a week. '
            f'Add one set of {name} ({entry.slot.day.name}).'
        ).strip(),
        action=add_set_action(entry),
        action_label=f'Add a set of {name}',
    )


def muscle_balance(ctx: RuleContext) -> list[Finding]:
    """
    Enough weekly volume for every focus area, and not too much pushing
    compared to pulling (keeps the shoulders healthy and the back wide)
    """
    if not ctx.entries:
        return []
    findings = []
    focus = ctx.goal.focus if ctx.goal else []
    for area in focus:
        if area in FOCUS_MUSCLES:
            findings.append(volume_finding(ctx, area))

    push = sum(ctx.weekly_sets(e) for e in ctx.entries if ctx.muscles(e) & PUSH_MUSCLES)
    pull_entries = [e for e in ctx.entries if ctx.muscles(e) & PULL_MUSCLES]
    pull = sum(ctx.weekly_sets(e) for e in pull_entries)
    if pull and push / pull > PUSH_PULL_MAX:
        candidates = [e for e in pull_entries if ctx.planned_sets(e) < MAX_SETS_PER_EXERCISE]
        if candidates:
            # Rows before pulldowns: the upper back is what balances pressing
            entry = max(candidates, key=lambda e: (len(ctx.muscles(e) & PULL_MUSCLES), e.pk))
            name = ctx.exercise_name(entry)
            findings.append(
                Finding(
                    key='balance:push_pull',
                    severity=Severity.ADJUST,
                    title=f'{push / pull:.1f}× more pushing than pulling',
                    body=(
                        f'About {push:.0f} sets of chest/triceps vs. {pull:.0f} of back/biceps a '
                        f'week. Keep it under {PUSH_PULL_MAX}× for healthy shoulders: add one set '
                        f'of {name}.'
                    ),
                    action=add_set_action(entry),
                    action_label=f'Add a set of {name}',
                )
            )
    return [f for f in findings if f is not None]


def stalled_lifts(ctx: RuleContext) -> list[Finding]:
    """
    Exercises without more weight or reps over the last STALL_SESSIONS sessions
    """
    findings = []
    for entry in ctx.entries:
        sessions = ctx.sessions.get(entry.pk, [])[-STALL_SESSIONS:]
        if len(sessions) < STALL_SESSIONS:
            continue

        def better(a, b) -> bool:
            if (a.weight or 0) != (b.weight or 0):
                return (a.weight or 0) > (b.weight or 0)
            return a.total_reps > b.total_reps

        if any(better(b, a) for a, b in zip(sessions, sessions[1:])):
            continue
        name = ctx.exercise_name(entry)
        findings.append(
            Finding(
                key=f'stalled:{entry.pk}',
                severity=Severity.INFO,
                title=f'{name} has stalled for {STALL_SESSIONS} sessions',
                body=(
                    'The program schedules a lighter session for it automatically. If it stalls '
                    'again after that, swap it for a variation (another angle or machine) and '
                    'check your sleep and protein.'
                ),
            )
        )
    return findings
