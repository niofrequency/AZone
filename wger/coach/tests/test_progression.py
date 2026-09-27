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

# Django
from django.contrib.auth.models import User

# Third Party
from rest_framework.test import APIClient

# wger
from wger.coach.seed import seed_program
from wger.coach.tests.test_seed import program_with_test_exercises
from wger.core.tests.base_testcase import WgerTestCase
from wger.manager.consts import (
    WEIGHT_UNIT_KG,
    WEIGHT_UNIT_LB,
)
from wger.manager.models import (
    SlotEntry,
    WorkoutLog,
)


class DoubleProgressionTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('lifter', password='lifter-password')
        self.routine = seed_program(self.user, program_with_test_exercises()).routine
        upper, lower = self.routine.days.filter(is_rest=False)

        # Incline press 4 x 8-10, +5 lb / hack squat 4 x 8-10, +10 lb / dips 3 x 10-12
        self.press = upper.slots.get(order=1).entries.get()
        self.dips = upper.slots.get(order=3).entries.get()
        self.hack_squat = lower.slots.get(order=1).entries.get()

    def log(self, entry, iteration, reps, weight=None, unit=WEIGHT_UNIT_LB, user=None):
        for r in reps:
            WorkoutLog.objects.create(
                user=user or self.user,
                exercise=entry.exercise,
                routine=self.routine,
                slot_entry=entry,
                iteration=iteration,
                repetitions=r,
                weight=weight,
                weight_unit_id=unit,
            )

    def target(self, entry, iteration):
        entry = SlotEntry.objects.get(pk=entry.pk)
        data = entry.get_config_data(iteration)
        return data.sets, data.weight, data.repetitions, data.max_repetitions

    def test_seeded_entries_use_double_progression(self):
        self.assertEqual(self.press.class_name, 'double_progression')
        self.assertEqual(self.press.config, {'increment': 5})
        self.assertEqual(self.hack_squat.config, {'increment': 10})

    def test_no_logs_keeps_the_prescription(self):
        self.assertEqual(self.target(self.press, 1), (4, None, 8, 10))
        self.assertEqual(self.target(self.press, 5), (4, None, 8, 10))

    def test_top_of_range_adds_weight(self):
        """4 x 10 at 70 lb -> next session 4 x 8-10 at 75 lb"""
        self.log(self.press, 1, [10, 10, 10, 10], 70)

        self.assertEqual(self.target(self.press, 2), (4, Decimal(75), 8, 10))

    def test_increment_per_exercise(self):
        self.log(self.hack_squat, 1, [10, 10, 10, 10], 180)

        self.assertEqual(self.target(self.hack_squat, 2), (4, Decimal(190), 8, 10))

    def test_hitting_the_target_adds_a_rep(self):
        """10, 10, 9, 8 at 70 lb: every set made 8 -> aim for 9-10 at the same weight"""
        self.log(self.press, 1, [10, 10, 9, 8], 70)

        self.assertEqual(self.target(self.press, 2), (4, Decimal(70), 9, 10))

    def test_missed_target_repeats(self):
        self.log(self.press, 1, [8, 7, 7, 6], 75)

        self.assertEqual(self.target(self.press, 2), (4, Decimal(75), 8, 10))

    def test_full_cycle(self):
        """Reps climb session by session until the weight goes up"""
        self.log(self.press, 1, [8, 8, 8, 8], 70)
        self.log(self.press, 2, [9, 9, 9, 9], 70)
        self.log(self.press, 3, [10, 10, 10, 10], 70)

        self.assertEqual(self.target(self.press, 2), (4, Decimal(70), 9, 10))
        self.assertEqual(self.target(self.press, 3), (4, Decimal(70), 10, None))
        self.assertEqual(self.target(self.press, 4), (4, Decimal(75), 8, 10))

    def test_deload_after_three_sessions_without_progress(self):
        self.log(self.press, 1, [9, 9, 8, 8], 75)
        self.log(self.press, 2, [9, 9, 8, 8], 75)
        self.log(self.press, 3, [8, 8, 8, 8], 75)

        entry = SlotEntry.objects.get(pk=self.press.pk)
        data = entry.get_config_data(4)
        self.assertEqual(data.weight, Decimal('67.5'))
        self.assertEqual(data.repetitions, 8)
        self.assertIn('Deload', data.comment)

        # The deload only lasts one session
        self.log(self.press, 4, [10, 10, 10, 10], Decimal('67.5'))
        data = SlotEntry.objects.get(pk=self.press.pk).get_config_data(5)
        self.assertEqual(data.weight, Decimal('72.5'))
        self.assertNotIn('Deload', data.comment)

    def test_follows_the_weight_actually_used(self):
        """The prescription said 75, but 80 was used for most sets"""
        self.log(self.press, 1, [10, 10, 10, 10], 70)
        self.log(self.press, 2, [8, 8, 8], 80)
        self.log(self.press, 2, [6], 75)

        self.assertEqual(self.target(self.press, 3), (4, Decimal(80), 8, 10))

    def test_kg_logs_are_converted(self):
        self.log(self.press, 1, [10, 10, 10, 10], 32, unit=WEIGHT_UNIT_KG)

        # 32 kg = 70.5 lb, rounded to 70 lb, +5
        self.assertEqual(self.target(self.press, 2)[1], Decimal(75))

    def test_bodyweight_exercise_progresses_reps(self):
        self.log(self.dips, 1, [10, 10, 10])
        self.log(self.dips, 2, [11, 11, 11])
        self.log(self.dips, 3, [12, 12, 12])

        self.assertEqual(self.target(self.dips, 2), (3, None, 11, 12))
        self.assertEqual(self.target(self.dips, 4), (3, None, 12, None))

    def test_weighted_dips_start_adding_weight(self):
        self.log(self.dips, 1, [12, 12, 12], 0)

        self.assertEqual(self.target(self.dips, 2), (3, Decimal(5), 10, 12))

    def test_other_users_logs_are_ignored(self):
        other = User.objects.get(username='test')
        self.log(self.press, 1, [10, 10, 10, 10], 100, user=other)

        self.assertEqual(self.target(self.press, 2), (4, None, 8, 10))

    def test_routine_api(self):
        """The progressed targets show up where the web UI and the app read them"""
        self.log(self.press, 1, [10, 10, 10, 10], 70)
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get(f'/api/v2/routine/{self.routine.pk}/date-sequence-display/')
        self.assertEqual(response.status_code, 200)

        press_targets = [
            (
                Decimal(s['weight']) if s['weight'] is not None else None,
                Decimal(s['repetitions']),
            )
            for day in response.json()
            if day['day'] and day['day']['name'] == 'Upper A'
            for slot in day['slots']
            for s in slot['sets']
            if s['slot_entry_id'] == self.press.pk
        ]
        self.assertEqual(press_targets[0], (None, 8))
        self.assertEqual(press_targets[1], (75, 8))
