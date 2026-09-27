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
from io import StringIO

# Django
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

# wger
from wger.coach import actions
from wger.coach.body import (
    CheckIn,
    save_check_in,
)
from wger.coach.models import (
    Recommendation,
    RecommendationStatus,
    Severity,
)
from wger.coach.rules import (
    evaluate,
    run_rules,
)
from wger.coach.rules.base import RuleContext
from wger.coach.seed import seed_program
from wger.coach.tests.test_seed import program_with_test_exercises
from wger.core.tests.base_testcase import WgerTestCase
from wger.exercises.models import (
    Exercise,
    Muscle,
)
from wger.manager.models import (
    SetsConfig,
    WorkoutLog,
)
from wger.nutrition.models import (
    Ingredient,
    LogItem,
)


TODAY = datetime.date(2026, 9, 27)


class RulesTestCase(WgerTestCase):
    """
    Seeds the program for a fresh user, with the test exercises given the
    muscles of the real ones so the volume rules see a realistic routine
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('lifter', password='lifter-password')
        self.user.userprofile.weight_unit = 'lb'
        self.user.userprofile.save()

        program = program_with_test_exercises()
        self.result = seed_program(
            self.user,
            program,
            start=TODAY - datetime.timedelta(days=21),
            current_weight=Decimal(180),
        )
        self.goal = self.result.goal
        self.upper = self.result.routine.days.get(name='Upper A')
        self.lower = self.result.routine.days.get(name='Lower B')

        # The test fixtures only have muscles 1-6
        for pk in range(7, 16):
            Muscle.objects.get_or_create(pk=pk, defaults={'name': f'Muscle {pk}', 'is_front': True})

        # Muscles of the real Upper A / Lower B exercises, in slot order
        upper = [{4}, {12}, {4, 5}, {1, 12, 9}, {2}, {5}]
        lower = [{10}, {11}, {10, 8, 11, 7}, {10}, {7}]
        for day, muscles in ((self.upper, upper), (self.lower, lower)):
            for slot, ids in zip(day.slots.order_by('order'), muscles):
                exercise = Exercise.objects.create(category_id=1)
                exercise.muscles.set(Muscle.objects.filter(pk__in=ids))
                slot.entries.update(exercise=exercise)

    def ctx(self):
        return RuleContext(self.user, today=TODAY)

    def keys(self):
        return {f.key: f for f in evaluate(self.ctx())}

    def weigh_in(self, values: list, end=TODAY):
        """One value per day, the last one on `end`"""
        with self.captureOnCommitCallbacks(execute=True):
            for i, value in enumerate(reversed(values)):
                save_check_in(
                    self.user,
                    CheckIn(date=end - datetime.timedelta(days=i), weight=Decimal(str(value))),
                )

    def two_weeks(self, previous, current):
        self.weigh_in([previous] * 7 + [current] * 7)


class WeightTrendTestCase(RulesTestCase):
    def test_needs_data(self):
        self.assertIn('weight_trend:need_data', self.keys())

    def test_on_track(self):
        self.two_weeks(180, 178.8)
        finding = self.keys()['weight_trend:on_track']
        self.assertEqual(finding.severity, Severity.GOOD)
        self.assertIn('1.2 lb/week', finding.title)

    def test_slow_cut_lowers_calories(self):
        self.two_weeks(180, 179.8)
        finding = self.keys()['weight_trend:slow']
        self.assertEqual(finding.severity, Severity.ADJUST)
        self.assertEqual(finding.action['delta'], -150)

    def test_slightly_slow(self):
        self.two_weeks(180, 179.3)
        self.assertEqual(self.keys()['weight_trend:slightly_slow'].severity, Severity.INFO)

    def test_fast_cut_raises_calories(self):
        self.two_weeks(180, 177.5)
        finding = self.keys()['weight_trend:fast']
        self.assertEqual(finding.severity, Severity.WARNING)
        self.assertEqual(finding.action['delta'], 150)

    def test_slow_bulk_raises_calories(self):
        self.goal.target_weight = Decimal(190)
        self.goal.save()
        self.two_weeks(180, 180.1)
        self.assertEqual(self.keys()['weight_trend:slow'].action['delta'], 150)

    def test_goal_reached(self):
        self.two_weeks(166, 164)
        self.assertIn('weight_trend:reached', self.keys())


class NutritionRuleTestCase(RulesTestCase):
    def log_days(self, grams, days=5):
        # 25.63 g protein and 300 kcal per 100 g
        ingredient = Ingredient.objects.get(name='Bachelor chow, now with flavour!')
        tz = self.user.userprofile.zone_info
        for i in range(1, days + 1):
            LogItem.objects.create(
                plan=self.result.plan,
                ingredient=ingredient,
                amount=grams,
                datetime=datetime.datetime.combine(
                    TODAY - datetime.timedelta(days=i), datetime.time(12), tzinfo=tz
                ),
            )

    def test_needs_data(self):
        self.assertIn('nutrition:need_data', self.keys())

    def test_protein_low(self):
        self.log_days(500)  # 128 g protein
        finding = self.keys()['nutrition:protein_low']
        self.assertIn('128 g of 165 g', finding.title)

    def test_protein_ok_calories_high(self):
        self.log_days(800)  # 205 g protein, 2,400 kcal
        keys = self.keys()
        self.assertEqual(keys['nutrition:protein_ok'].title, 'Protein on target: 205 g a day')
        self.assertIn('nutrition:calories_high', keys)


class BodyRuleTestCase(RulesTestCase):
    def measure(self, date, waist, shoulders):
        with self.captureOnCommitCallbacks(execute=True):
            save_check_in(
                self.user,
                CheckIn(
                    date=date, parts={'waist': Decimal(waist), 'shoulders': Decimal(shoulders)}
                ),
            )

    def test_needs_data(self):
        self.assertIn('v_taper:need_data', self.keys())

    def test_waist_down_shoulders_flat(self):
        self.measure(TODAY - datetime.timedelta(weeks=3), 34.5, 48)
        self.measure(TODAY, 33.5, 48)
        keys = self.keys()

        self.assertIn('v_taper:status', keys)
        self.assertIn('v_taper:waist_down', keys)
        # Flat shoulders: more side delt volume
        self.assertEqual(keys['volume:side_delts'].severity, Severity.ADJUST)

    def test_target_reached(self):
        self.measure(TODAY, 30, 49)
        self.assertIn('v_taper:reached', self.keys())


class TrainingRuleTestCase(RulesTestCase):
    def test_volume_and_balance(self):
        keys = self.keys()

        # Lateral raises: 4 sets every 3 days = ~9 sets a week
        side_delts = keys['volume:side_delts']
        self.assertIn('about 9 sets', side_delts.title)
        lateral = self.upper.slots.get(order=5).entries.get()
        self.assertEqual(side_delts.action, {'type': 'add_set', 'slot_entry': lateral.pk})

        # Chest press, dips, pushdowns vs. pulldown, row
        push_pull = keys['balance:push_pull']
        row = self.upper.slots.get(order=4).entries.get()
        self.assertEqual(push_pull.action['slot_entry'], row.pk)

        # Lats: 8 sets per cycle is plenty
        self.assertNotIn('volume:lats', keys)
        self.assertIn('volume:abs', keys)

    def test_stalled_lift(self):
        entry = self.lower.slots.get(order=1).entries.get()
        for iteration in (1, 2, 3):
            for _ in range(4):
                WorkoutLog.objects.create(
                    user=self.user,
                    exercise=entry.exercise,
                    routine=self.result.routine,
                    slot_entry=entry,
                    iteration=iteration,
                    repetitions=8,
                    weight=180,
                )
        self.assertIn(f'stalled:{entry.pk}', self.keys())


class EngineTestCase(RulesTestCase):
    def test_run_rules_syncs_recommendations(self):
        pending = run_rules(self.user, today=TODAY)
        keys = {r.key for r in pending}
        self.assertIn('weight_trend:need_data', keys)

        # Running again updates instead of duplicating
        run_rules(self.user, today=TODAY)
        self.assertEqual(
            Recommendation.objects.filter(user=self.user, key='weight_trend:need_data').count(), 1
        )

        # A finding that stops firing disappears
        self.two_weeks(180, 178.8)
        keys = {r.key for r in run_rules(self.user, today=TODAY)}
        self.assertNotIn('weight_trend:need_data', keys)
        self.assertIn('weight_trend:on_track', keys)

    def test_dismissed_stays_quiet(self):
        run_rules(self.user, today=TODAY)
        rec = Recommendation.objects.get(user=self.user, key='volume:side_delts')
        actions.dismiss(rec)

        keys = {r.key for r in run_rules(self.user, today=TODAY)}
        self.assertNotIn('volume:side_delts', keys)

        # After the quiet period it comes back
        Recommendation.objects.filter(pk=rec.pk).update(
            resolved=timezone.now() - datetime.timedelta(days=15)
        )
        keys = {r.key for r in run_rules(self.user, today=TODAY)}
        self.assertIn('volume:side_delts', keys)

    def test_apply_add_set(self):
        run_rules(self.user, today=TODAY)
        rec = Recommendation.objects.get(user=self.user, key='volume:side_delts')
        lateral = self.upper.slots.get(order=5).entries.get()

        message = actions.apply(rec)

        self.assertIn('now has 5 sets', message)
        self.assertEqual(lateral.get_config_data(1).sets, 5)
        rec.refresh_from_db()
        self.assertEqual(rec.status, RecommendationStatus.APPLIED)

        with self.assertRaises(actions.ActionError):
            actions.apply(rec)

    def test_apply_add_set_starts_with_next_session(self):
        lateral = self.upper.slots.get(order=5).entries.get()
        WorkoutLog.objects.create(
            user=self.user,
            exercise=lateral.exercise,
            routine=self.result.routine,
            slot_entry=lateral,
            iteration=1,
            repetitions=12,
            weight=15,
        )
        rec = Recommendation.objects.create(
            user=self.user,
            key='volume:side_delts',
            severity=Severity.ADJUST,
            title='t',
            action={'type': 'add_set', 'slot_entry': lateral.pk},
        )
        actions.apply(rec)

        self.assertEqual(lateral.get_config_data(1).sets, 4)
        self.assertEqual(lateral.get_config_data(2).sets, 5)
        self.assertTrue(SetsConfig.objects.filter(slot_entry=lateral, iteration=2).exists())

    def test_apply_calories(self):
        plan = self.result.plan
        rec = Recommendation.objects.create(
            user=self.user,
            key='weight_trend:slow',
            severity=Severity.ADJUST,
            title='t',
            action={'type': 'calories', 'plan': str(plan.pk), 'delta': -150},
        )
        self.assertEqual(actions.apply(rec), 'Calorie goal is now 1750 kcal.')
        plan.refresh_from_db()
        self.assertEqual(plan.goal_energy, 1750)
        self.assertEqual(plan.goal_carbohydrates, 165 - 38)

    def test_actions_are_scoped_to_the_owner(self):
        other = User.objects.get(username='test')
        lateral = self.upper.slots.get(order=5).entries.get()
        rec = Recommendation.objects.create(
            user=other,
            key='x',
            severity=Severity.ADJUST,
            title='t',
            action={'type': 'add_set', 'slot_entry': lateral.pk},
        )
        with self.assertRaises(actions.ActionError):
            actions.apply(rec)

    def test_command(self):
        out = StringIO()
        call_command('coach_run_rules', stdout=out)
        self.assertIn('lifter:', out.getvalue())


class DashboardViewTestCase(RulesTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='lifter', password='lifter-password')

    def test_dashboard(self):
        self.two_weeks(180, 178.8)
        response = self.client.get(reverse('coach:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'What to work on')
        self.assertContains(response, 'Add a set of')
        self.assertContains(response, '7-day average weight')
        self.assertContains(response, 'Next workout')

    def test_dashboard_without_anything(self):
        User.objects.create_user('new', password='new-password')
        self.client.login(username='new', password='new-password')

        response = self.client.get(reverse('coach:dashboard'))
        self.assertContains(response, 'Set a goal')

    def test_apply_and_dismiss(self):
        self.client.get(reverse('coach:dashboard'))
        rec = Recommendation.objects.get(user=self.user, key='volume:side_delts')

        self.assertEqual(self.client.get(reverse('coach:apply', args=[rec.pk])).status_code, 405)
        response = self.client.post(reverse('coach:apply', args=[rec.pk]), follow=True)
        self.assertContains(response, 'now has 5 sets')

        rec = Recommendation.objects.get(user=self.user, key='balance:push_pull')
        self.client.post(reverse('coach:dismiss', args=[rec.pk]))
        rec.refresh_from_db()
        self.assertEqual(rec.status, RecommendationStatus.DISMISSED)

    def test_other_users_recommendation(self):
        self.client.get(reverse('coach:dashboard'))
        rec = Recommendation.objects.filter(user=self.user).first()

        User.objects.create_user('other', password='other-password')
        self.client.login(username='other', password='other-password')
        response = self.client.post(reverse('coach:apply', args=[rec.pk]))
        self.assertEqual(response.status_code, 404)
