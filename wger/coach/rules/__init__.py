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
The coach's rules engine: every rule reads the user's data through a
RuleContext and returns Findings, which are stored as Recommendations.

* a finding that keeps firing updates its pending recommendation
* a pending recommendation whose finding stopped firing is removed
* a dismissed one stays quiet for DISMISS_DAYS, an applied one for APPLY_DAYS
"""

# Standard Library
import datetime
import logging

# Django
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

# wger
from wger.coach.models import (
    Recommendation,
    RecommendationStatus,
)
from wger.coach.rules.base import (
    Finding,
    RuleContext,
)
from wger.coach.rules.body import v_taper
from wger.coach.rules.nutrition import nutrition
from wger.coach.rules.training import (
    muscle_balance,
    stalled_lifts,
)
from wger.coach.rules.weight_trend import weight_trend


logger = logging.getLogger(__name__)

RULES = [
    weight_trend,
    nutrition,
    v_taper,
    muscle_balance,
    stalled_lifts,
]

DISMISS_DAYS = 14
APPLY_DAYS = 7


def evaluate(ctx: RuleContext) -> list[Finding]:
    """
    All findings, the first one wins when two rules report the same key
    """
    findings = {}
    for rule in RULES:
        try:
            results = rule(ctx)
        except Exception:
            # One broken rule must not take the dashboard down
            logger.exception(f'Coach rule {rule.__name__} failed for user {ctx.user.pk}')
            continue
        for finding in results:
            finding.rule = finding.rule or rule.__name__
            findings.setdefault(finding.key, finding)
    return list(findings.values())


def run_rules(user: User, today: datetime.date | None = None) -> list[Recommendation]:
    """
    Evaluates all rules and syncs the user's recommendations. Returns the
    pending ones
    """
    ctx = RuleContext(user, today=today)
    findings = evaluate(ctx)
    now = timezone.now()

    with transaction.atomic():
        existing = {}
        for rec in Recommendation.objects.filter(user=user).order_by('created'):
            existing[rec.key] = rec  # newest per key wins

        for finding in findings:
            rec = existing.get(finding.key)
            if rec is not None and rec.status != RecommendationStatus.PENDING:
                quiet = DISMISS_DAYS if rec.status == RecommendationStatus.DISMISSED else APPLY_DAYS
                if rec.resolved and now - rec.resolved < datetime.timedelta(days=quiet):
                    continue
                rec = None

            if rec is None:
                rec = Recommendation(user=user, key=finding.key)
            rec.rule = finding.rule
            rec.severity = finding.severity
            rec.title = finding.title
            rec.body = finding.body
            rec.action = finding.action
            rec.action_label = finding.action_label
            rec.status = RecommendationStatus.PENDING
            rec.resolved = None
            rec.save()

        keys = {f.key for f in findings}
        Recommendation.objects.filter(user=user, status=RecommendationStatus.PENDING).exclude(
            key__in=keys
        ).delete()

    return list(Recommendation.objects.filter(user=user, status=RecommendationStatus.PENDING))
