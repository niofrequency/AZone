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
import dataclasses
import datetime
import json
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

# Django
from django.contrib.auth.models import User
from django.core.management import (
    CommandError,
    call_command,
)

# Third Party
from rest_framework.test import APIClient

# wger
from wger.coach.programs.aesthetic165 import PROGRAM
from wger.coach.programs.base import ProgramSpec
from wger.coach.seed import (
    ProgramError,
    seed_program,
)
from wger.core.tests.base_testcase import WgerTestCase
from wger.exercises.models import Exercise
from wger.manager.consts import WEIGHT_UNIT_LB
from wger.manager.models import (
    WorkoutLog,
    WorkoutSession,
)
from wger.measurements.models import (
    Category,
    Measurement,
)
from wger.nutrition.models import (
    LogItem,
    NutritionPlan,
)


def program_with_test_exercises() -> ProgramSpec:
    """
    The real program, with its exercises swapped for the ones in the test fixtures
    """
    uuids = [str(u) for u in Exercise.objects.order_by('pk').values_list('uuid', flat=True)]
    counter = iter(range(1000))

    def swap(day):
        exercises = [
            dataclasses.replace(e, uuid=uuids[next(counter) % len(uuids)]) for e in day.exercises
        ]
        return dataclasses.replace(day, exercises=exercises)

    return dataclasses.replace(PROGRAM, days=[swap(day) for day in PROGRAM.days])


class ProgramDataTestCase(WgerTestCase):
    def test_exercises_exist_in_exercise_database(self):
        """
        Every exercise of the program is part of the exercise data loaded by
        `wger bootstrap`
        """
        path = Path(__file__).parents[2] / 'exercises' / 'fixtures' / 'exercise-base-data.json'
        fixture_uuids = {row['fields']['uuid'] for row in json.loads(path.read_text())}

        for day in PROGRAM.days:
            for exercise in day.exercises:
                self.assertIn(exercise.uuid, fixture_uuids, exercise.name)

    def test_program_matches_prd(self):
        self.assertEqual([d.name for d in PROGRAM.days], ['Upper A', 'Lower B'])
        self.assertEqual(len(PROGRAM.days[0].exercises), 6)
        self.assertEqual(len(PROGRAM.days[1].exercises), 5)
        self.assertTrue(150 <= PROGRAM.nutrition.protein <= 175)
        self.assertTrue(1800 <= PROGRAM.nutrition.energy <= 2000)


class SeedProgramTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('lifter', password='lifter-password')
        self.program = program_with_test_exercises()
        self.start = datetime.date(2026, 9, 28)

    def test_creates_routine(self):
        result = seed_program(self.user, self.program, start=self.start)
        routine = result.routine

        self.assertEqual(routine.name, 'Aesthetic 165')
        self.assertEqual(routine.start, self.start)
        self.assertEqual(routine.end, datetime.date(2026, 12, 20))

        days = list(routine.days.all())
        self.assertEqual([d.name for d in days], ['Upper A', 'Lower B', 'Rest'])
        self.assertTrue(days[2].is_rest)
        self.assertEqual(days[0].slots.count(), 6)
        self.assertEqual(days[1].slots.count(), 5)

        # Targets for the first exercise: incline press 4 x 8-10 @ RIR 2, 120 s rest
        slot = days[0].slots.first()
        self.assertIn('Deep stretch', slot.comment)
        entry = slot.entries.first()
        self.assertEqual(entry.weight_unit_id, WEIGHT_UNIT_LB)
        config = entry.get_config_data(1)
        self.assertEqual(config.sets, 4)
        self.assertEqual(config.repetitions, 8)
        self.assertEqual(config.max_repetitions, 10)
        self.assertEqual(config.rir, 2)
        self.assertEqual(config.rest, 120)

    def test_days_cycle_with_rest(self):
        routine = seed_program(self.user, self.program, start=self.start).routine
        names = [d.day.name for d in routine.date_sequence[:6]]
        self.assertEqual(names, ['Upper A', 'Lower B', 'Rest', 'Upper A', 'Lower B', 'Rest'])

    def test_creates_nutrition_plan(self):
        plan = seed_program(self.user, self.program, start=self.start).plan

        self.assertTrue(plan.has_goal_calories)
        self.assertEqual(plan.goal_energy, 1900)
        self.assertEqual(plan.goal_protein, 165)
        self.assertEqual(plan.goal_carbohydrates, 165)
        self.assertEqual(plan.goal_fat, 52)
        self.assertEqual(
            [m.name for m in plan.meal_set.order_by('order')],
            ['Breakfast', 'Lunch', 'Pre-workout', 'Dinner'],
        )

    def test_creates_measurements_and_body_weight(self):
        result = seed_program(
            self.user,
            self.program,
            start=self.start,
            current_weight=Decimal('179'),
        )

        names = {c.name for c in Category.objects.filter(user=self.user)}
        self.assertTrue({'Waist', 'Chest', 'Shoulders', 'Arms', 'Thighs', 'Steps'} <= names)
        self.assertEqual(Category.objects.get(user=self.user, name='Steps').metric_type, 'steps')

        self.assertEqual(result.body_weight.value, Decimal('179'))
        self.assertEqual(result.body_weight.category.metric_type, 'body_weight')
        self.user.userprofile.refresh_from_db()
        self.assertEqual(self.user.userprofile.weight_unit, 'lb')

    def test_existing_program_needs_replace(self):
        seed_program(self.user, self.program, start=self.start)
        with self.assertRaises(ProgramError):
            seed_program(self.user, self.program, start=self.start)

    def test_replace_keeps_logs(self):
        result = seed_program(self.user, self.program, start=self.start)
        entry = result.routine.days.first().slots.first().entries.first()
        log = WorkoutLog.objects.create(
            user=self.user,
            exercise=entry.exercise,
            routine=result.routine,
            slot_entry=entry,
            iteration=1,
            repetitions=10,
            weight=70,
        )
        diary = LogItem.objects.create(plan=result.plan, ingredient_id=1, amount=100)

        seed_program(self.user, self.program, start=self.start, replace=True)

        self.assertTrue(WorkoutLog.objects.filter(pk=log.pk).exists())
        self.assertTrue(LogItem.objects.filter(pk=diary.pk).exists())
        self.assertEqual(NutritionPlan.objects.filter(user=self.user).count(), 1)
        self.assertEqual(result.plan.meal_set.count(), 4)

    def test_missing_exercise(self):
        broken_day = dataclasses.replace(
            self.program.days[0],
            exercises=[
                dataclasses.replace(
                    self.program.days[0].exercises[0],
                    uuid='00000000-0000-0000-0000-000000000000',
                )
            ],
        )
        program = dataclasses.replace(self.program, days=[broken_day])

        with self.assertRaises(ProgramError):
            seed_program(self.user, program)
        self.assertFalse(Measurement.objects.filter(category__user=self.user).exists())


class SeedCommandTestCase(WgerTestCase):
    def call(self, *args):
        out = StringIO()
        with mock.patch(
            'wger.coach.management.commands.seed_aesthetic165.PROGRAM',
            program_with_test_exercises(),
        ):
            call_command('seed_aesthetic165', *args, stdout=out)
        return out.getvalue()

    def test_command(self):
        out = self.call('--user', 'test', '--start', '2026-09-28', '--current-weight', '179')

        self.assertIn('"Aesthetic 165" is set up for test', out)
        self.assertIn('Upper A: 6 exercises', out)
        self.assertIn('165 g protein', out)
        self.assertIn('179 lb logged', out)

    def test_command_errors(self):
        with self.assertRaisesMessage(CommandError, 'does not exist'):
            self.call('--user', 'nobody')
        with self.assertRaisesMessage(CommandError, '--start'):
            self.call('--user', 'test', '--start', 'tomorrow')
        with self.assertRaisesMessage(CommandError, '--current-weight'):
            self.call('--user', 'test', '--current-weight', 'heavy')

        self.call('--user', 'test')
        with self.assertRaisesMessage(CommandError, '--replace'):
            self.call('--user', 'test')
        self.assertIn('is set up', self.call('--user', 'test', '--replace'))


class LoggingTestCase(WgerTestCase):
    """
    Milestone 1: a user can log an Upper A workout and a meal against the
    seeded program through wger's regular API
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('lifter', password='lifter-password')
        self.result = seed_program(self.user, program_with_test_exercises())
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_log_upper_a_workout(self):
        day = self.result.routine.days.get(name='Upper A')
        entry = day.slots.first().entries.first()

        response = self.client.post(
            '/api/v2/workoutsession/',
            {'routine': self.result.routine.pk, 'day': day.pk, 'impression': '3'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        session_id = response.json()['id']

        for weight, reps in ((70, 10), (75, 8)):
            response = self.client.post(
                '/api/v2/workoutlog/',
                {
                    'session': session_id,
                    'routine': self.result.routine.pk,
                    'slot_entry': entry.pk,
                    'exercise': entry.exercise_id,
                    'iteration': 1,
                    'weight': weight,
                    'weight_unit': WEIGHT_UNIT_LB,
                    'repetitions': reps,
                    'repetitions_unit': 1,
                    'rir': 2,
                },
                format='json',
            )
            self.assertEqual(response.status_code, 201, response.content)

        session = WorkoutSession.objects.get(pk=session_id)
        self.assertEqual(session.day, day)
        self.assertEqual(
            list(WorkoutLog.objects.filter(session=session).values_list('weight', 'repetitions')),
            [(Decimal('70'), Decimal('10')), (Decimal('75'), Decimal('8'))],
        )

    def test_log_meal(self):
        breakfast = self.result.plan.meal_set.get(name='Breakfast')

        response = self.client.post(
            '/api/v2/nutritiondiary/',
            {
                'plan': str(self.result.plan.pk),
                'meal': str(breakfast.pk),
                'ingredient': 1,
                'amount': 150,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(LogItem.objects.filter(plan=self.result.plan, meal=breakfast).count(), 1)
