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

# wger
from wger.coach.body import VTAPER_TARGET
from wger.coach.models import Severity
from wger.coach.rules.base import (
    Finding,
    RuleContext,
)
from wger.coach.rules.training import volume_finding


MIN_WEEKS = 3


def change_since(points, today: datetime.date, weeks: int):
    """
    Latest value minus the latest one at least `weeks` weeks older, or None
    """
    if len(points) < 2:
        return None
    latest = points[-1]
    cutoff = latest.date - datetime.timedelta(weeks=weeks)
    older = [p for p in points if p.date <= cutoff]
    if not older:
        return None
    return latest.value - older[-1].value, older[-1].date


def v_taper(ctx: RuleContext) -> list[Finding]:
    """
    Tracks the shoulder-to-waist ratio: the waist should come down on a cut,
    the shoulders should hold or grow
    """
    ratio = ctx.ratio_series
    if not ratio:
        return [
            Finding(
                key='v_taper:need_data',
                severity=Severity.INFO,
                title='Measure your waist and shoulders',
                body=(
                    'Add them to your weekly check-in. The coach tracks your shoulder-to-waist '
                    f'ratio (V-taper) against the {VTAPER_TARGET} target.'
                ),
            )
        ]

    findings = []
    latest = ratio[-1].value
    unit = ctx.body_categories['waist'].unit
    waist = change_since(ctx.body_series('waist'), ctx.today, MIN_WEEKS)
    shoulders = change_since(ctx.body_series('shoulders'), ctx.today, MIN_WEEKS)
    losing_weight = ctx.goal is not None and ctx.goal.is_cut

    if latest >= VTAPER_TARGET:
        findings.append(
            Finding(
                key='v_taper:reached',
                severity=Severity.GOOD,
                title=f'V-taper ratio {latest:.2f}, at the {VTAPER_TARGET} target',
                body='Keep shoulders and lats progressing while the waist stays tight.',
            )
        )
    else:
        gap = VTAPER_TARGET - latest
        findings.append(
            Finding(
                key='v_taper:status',
                severity=Severity.INFO,
                title=f'V-taper ratio {latest:.2f} (target {VTAPER_TARGET})',
                body=(
                    f'{gap:.2f} to go. On a cut most of it comes from the waist; side delt and lat '
                    'volume builds the rest.'
                ),
            )
        )

    if waist is not None:
        change, since = waist
        if change < 0:
            findings.append(
                Finding(
                    key='v_taper:waist_down',
                    severity=Severity.GOOD,
                    title=f'Waist down {abs(change):.1f} {unit} since {since:%b %-d}',
                    body='Fat is coming off the midsection.',
                )
            )
        elif losing_weight:
            findings.append(
                Finding(
                    key='v_taper:waist_flat',
                    severity=Severity.INFO,
                    title=f"Waist hasn't moved since {since:%b %-d}",
                    body=(
                        'Measure at the navel, in the morning, relaxed. If the scale is dropping, '
                        'the waist usually follows within a few weeks.'
                    ),
                )
            )

    if shoulders is not None and latest < VTAPER_TARGET:
        change, since = shoulders
        if change <= 0:
            findings.append(_add_side_delt_volume(ctx, since))
    return [f for f in findings if f is not None]


def _add_side_delt_volume(ctx: RuleContext, since: datetime.date) -> Finding | None:
    # Shares its key with the volume rule, so the two never suggest it twice
    return volume_finding(
        ctx,
        'side_delts',
        reason=f"Your shoulders haven't grown since {since:%b %-d}.",
    )
