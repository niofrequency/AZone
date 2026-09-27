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

# Django
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.views.decorators.http import require_POST

# wger
from wger.coach import (
    actions,
    charts,
    dashboard as dashboard_data,
)
from wger.coach.body import (
    BODY_PARTS,
    VTAPER_TARGET,
    CheckIn,
    Point,
    body_categories,
    category_series,
    check_in_history,
    moving_average,
    save_check_in,
    vtaper_category,
    weight_series,
)
from wger.coach.forms import (
    CheckInForm,
    GoalForm,
)
from wger.coach.models import (
    CoachGoal,
    Recommendation,
    RecommendationStatus,
    Severity,
)
from wger.coach.rules import run_rules
from wger.coach.rules.base import RuleContext


def get_goal(user) -> CoachGoal | None:
    return CoachGoal.objects.filter(user=user).first()


def weight_chart(user, goal: CoachGoal | None) -> charts.Chart:
    unit = user.userprofile.weight_unit
    weights = weight_series(user)
    series = [
        charts.Series('daily', 'Daily weigh-in', weights, style='dots'),
        charts.Series('average', '7-day average', moving_average(weights)),
    ]
    if goal is not None and goal.start_weight is None and weights:
        # No start weight given: the first weigh-in since the start counts
        first = next((p for p in weights if p.date >= goal.start_date), weights[-1])
        goal.start_weight = first.value
    if goal is not None and goal.start_weight is not None and weights:
        # Only the stretch of the plan next to the data, the full line to the
        # target date would squeeze weeks of weigh-ins into a corner
        end = min(goal.target_date, weights[-1].date + datetime.timedelta(weeks=2))
        start = max(goal.start_date, weights[0].date)
        if end > start:
            plan = [
                Point(start, goal.planned_weight(start)),
                Point(end, goal.planned_weight(end)),
            ]
            series.append(charts.Series('plan', 'Plan', plan, style='reference'))
    return charts.build(
        charts.Chart(id='chart-weight', title='Body weight', unit=unit, series=series)
    )


def vtaper_chart(user, categories) -> charts.Chart:
    ratio = category_series(user, vtaper_category(user, categories))
    return charts.build(
        charts.Chart(
            id='chart-vtaper',
            title='Shoulder-to-waist ratio',
            unit='',
            decimals=2,
            series=[charts.Series('ratio', 'Shoulder:waist', ratio)],
            reference_value=VTAPER_TARGET,
            reference_label=f'Target {VTAPER_TARGET}',
        )
    )


def waist_chart(user, categories) -> charts.Chart:
    waist = categories['waist']
    return charts.build(
        charts.Chart(
            id='chart-waist',
            title='Waist',
            unit=waist.unit,
            series=[charts.Series('waist', 'Waist', category_series(user, waist))],
        )
    )


@login_required
def check_in(request):
    user = request.user
    categories = body_categories(user)
    weight_unit = user.userprofile.weight_unit
    length_unit = categories['waist'].unit or 'in'

    if request.method == 'POST':
        form = CheckInForm(
            request.POST,
            request.FILES,
            weight_unit=weight_unit,
            length_unit=length_unit,
        )
        if form.is_valid():
            data = form.cleaned_data
            save_check_in(
                user,
                CheckIn(
                    date=data['date'],
                    weight=data['weight'],
                    parts={part.key: data[part.key] for part in BODY_PARTS},
                    photo=data['photo'],
                    notes=data['notes'],
                ),
            )
            messages.success(request, f'Check-in for {data["date"]:%b %-d} saved.')
            return redirect('coach:check-in')
    else:
        form = CheckInForm(weight_unit=weight_unit, length_unit=length_unit)

    goal = get_goal(user)
    context = {
        'form': form,
        'goal': goal,
        'weight_unit': weight_unit,
        'length_unit': length_unit,
        'body_parts': BODY_PARTS,
        'history': [
            {
                'date': row['date'],
                'weight': row.get('weight'),
                'parts': [row.get(part.key) for part in BODY_PARTS],
                'ratio': row.get('ratio'),
            }
            for row in check_in_history(user)
        ],
        'charts': [
            weight_chart(user, goal),
            vtaper_chart(user, categories),
            waist_chart(user, categories),
        ],
        'vtaper_target': VTAPER_TARGET,
    }
    return render(request, 'coach/check_in.html', context)


@login_required
def goal(request):
    user = request.user
    instance = get_goal(user)
    unit = user.userprofile.weight_unit

    if request.method == 'POST':
        form = GoalForm(request.POST, instance=instance, unit=unit)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = user
            goal.weight_unit = unit
            goal.save()
            messages.success(request, 'Your goal is saved.')
            return redirect('coach:check-in')
    else:
        initial = {}
        if instance is None:
            weights = weight_series(user)
            today = timezone.localdate()
            initial = {
                'start_date': today,
                'start_weight': weights[-1].value if weights else None,
                'target_date': today + datetime.timedelta(weeks=12),
                'rate_min_per_week': 1.0 if unit == 'lb' else 0.5,
                'rate_max_per_week': 1.5 if unit == 'lb' else 0.7,
            }
        form = GoalForm(instance=instance, initial=initial, unit=unit)

    return render(request, 'coach/goal.html', {'form': form, 'goal': instance, 'unit': unit})


@login_required
def dashboard(request):
    user = request.user
    goal = get_goal(user)
    recommendations = run_rules(user)
    ctx = RuleContext(user)

    todo = [r for r in recommendations if r.severity in (Severity.ADJUST, Severity.WARNING)]
    status = [r for r in recommendations if r.severity in (Severity.GOOD, Severity.INFO)]
    order = {Severity.WARNING: 0, Severity.ADJUST: 1, Severity.INFO: 2, Severity.GOOD: 3}

    context = {
        'goal': goal,
        'tiles': dashboard_data.tiles(ctx),
        'todo': sorted(todo, key=lambda r: order[r.severity]),
        'status': sorted(status, key=lambda r: order[r.severity]),
        'chart': weight_chart(user, goal),
        'next_workout': dashboard_data.next_workout(ctx),
        'routine': ctx.routine,
        'progress': dashboard_data.recent_progress(ctx),
        'plan': ctx.plan,
    }
    return render(request, 'coach/dashboard.html', context)


def _pending(request, pk) -> Recommendation:
    return get_object_or_404(
        Recommendation,
        pk=pk,
        user=request.user,
        status=RecommendationStatus.PENDING,
    )


@login_required
@require_POST
def apply_recommendation(request, pk):
    recommendation = _pending(request, pk)
    try:
        messages.success(request, actions.apply(recommendation))
    except actions.ActionError as e:
        messages.error(request, str(e))
    return redirect('coach:dashboard')


@login_required
@require_POST
def dismiss_recommendation(request, pk):
    actions.dismiss(_pending(request, pk))
    return redirect('coach:dashboard')
