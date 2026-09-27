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

# Django
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

# wger
from wger.coach.body import (
    steps_series,
    weight_series,
)
from wger.coach.models import (
    CardioSession,
    CoachGoal,
)
from wger.core.tests.base_testcase import WgerTestCase
from wger.gallery.models import Image


class CheckInViewTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('lifter', password='lifter-password')
        self.user.userprofile.weight_unit = 'lb'
        self.user.userprofile.save()
        self.client.login(username='lifter', password='lifter-password')
        self.url = reverse('coach:check-in')

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_empty_page(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Weekly check-in')
        self.assertContains(response, 'Set a goal')
        self.assertContains(response, 'No entries yet')

    def test_check_in(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                self.url,
                {
                    'date': '2026-09-20',
                    'weight': '178.4',
                    'waist': '32',
                    'shoulders': '48',
                    'notes': '',
                },
            )
        self.assertRedirects(response, self.url)

        response = self.client.get(self.url)
        self.assertContains(response, '178.4 lb')
        self.assertContains(response, '1.50')
        self.assertContains(response, 'chart-weight-data')

    def test_photo(self):
        with open('wger/exercises/tests/protestschwein.jpg', 'rb') as f:
            photo = SimpleUploadedFile('front.jpg', f.read(), content_type='image/jpeg')

        response = self.client.post(
            self.url,
            {'date': '2026-09-20', 'photo': photo, 'notes': 'Front, relaxed'},
        )

        self.assertRedirects(response, self.url)
        image = Image.objects.get(user=self.user)
        self.assertEqual(image.date, datetime.date(2026, 9, 20))
        self.assertEqual(image.description, 'Front, relaxed')

    def test_validation(self):
        response = self.client.post(self.url, {'date': '2026-09-20'})
        self.assertContains(response, 'Enter at least one value or a photo')

        response = self.client.post(self.url, {'date': '2026-09-20', 'weight': '5'})
        self.assertContains(response, 'Enter a weight between')

        response = self.client.post(self.url, {'date': '2026-09-20', 'waist': '900'})
        self.assertContains(response, 'Enter a value between')

        response = self.client.post(self.url, {'date': '2099-01-01', 'weight': '170'})
        self.assertContains(response, 'cannot be in the future')

        self.assertEqual(weight_series(self.user), [])


class GoalViewTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('lifter', password='lifter-password')
        self.user.userprofile.weight_unit = 'lb'
        self.user.userprofile.save()
        self.client.login(username='lifter', password='lifter-password')
        self.url = reverse('coach:goal')

    def data(self, **kwargs):
        return {
            'start_date': '2026-09-01',
            'start_weight': '179',
            'target_weight': '165',
            'target_date': '2026-11-24',
            'rate_min_per_week': '1.0',
            'rate_max_per_week': '1.5',
            'protein_target': '165',
            'step_target': '10000',
            'focus': ['upper_chest', 'lats'],
            **kwargs,
        }

    def test_create_and_edit(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

        response = self.client.post(self.url, self.data())
        self.assertRedirects(response, reverse('coach:check-in'))
        goal = CoachGoal.objects.get(user=self.user)
        self.assertEqual(goal.target_weight, Decimal(165))
        self.assertEqual(goal.weight_unit, 'lb')
        self.assertEqual(goal.focus, ['upper_chest', 'lats'])

        self.client.post(self.url, self.data(target_weight='168'))
        self.assertEqual(CoachGoal.objects.get(user=self.user).target_weight, Decimal(168))

    def test_validation(self):
        response = self.client.post(self.url, self.data(target_date='2026-08-01'))
        self.assertContains(response, 'has to be after the start date')

        response = self.client.post(self.url, self.data(rate_max_per_week='0.5'))
        self.assertContains(response, 'at least the slowest weekly change')

        self.assertFalse(CoachGoal.objects.filter(user=self.user).exists())

    def test_goal_without_start_weight_uses_first_weigh_in(self):
        self.client.post(self.url, self.data(start_weight=''))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('coach:check-in'), {'date': '2026-09-02', 'weight': '180'})

        response = self.client.get(reverse('coach:check-in'))
        self.assertContains(response, 'Plan')


class CardioViewTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('lifter', password='lifter-password')
        self.user.userprofile.weight_unit = 'lb'
        self.user.userprofile.save()
        self.client.login(username='lifter', password='lifter-password')
        self.url = reverse('coach:cardio')

    def post(self, **data):
        return self.client.post(
            self.url,
            {'date': '2026-09-20', 'kind': 'incline_walk', 'timing': 'morning', **data},
        )

    def test_empty_page(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Cardio &amp; steps')
        self.assertContains(response, 'Nothing logged yet')

    def test_steps_and_cardio(self):
        response = self.post(steps='10432', duration='35', incline='12', speed='3.2')
        self.assertRedirects(response, self.url)

        self.assertEqual(steps_series(self.user)[0].value, Decimal(10432))
        session = CardioSession.objects.get(user=self.user)
        self.assertEqual(session.summary, '35 min · 12% incline · 3.2 mph')
        self.assertEqual(session.speed_unit, 'mph')

        # Same day again: steps are corrected, a second cardio session is added
        self.post(steps='11000', duration='20', timing='post_workout')
        self.assertEqual([p.value for p in steps_series(self.user)], [Decimal(11000)])
        self.assertEqual(CardioSession.objects.filter(user=self.user).count(), 2)

    def test_steps_only(self):
        self.assertRedirects(self.post(steps='8000'), self.url)

    def test_validation(self):
        self.assertContains(self.post(), 'Enter your steps, a cardio duration, or both')
        self.assertContains(self.post(steps='-5'), 'greater than or equal to 0')
        self.assertContains(self.post(duration='35', incline='80'), 'less than or equal to 40')

    def test_kg_users_log_kmh(self):
        self.user.userprofile.weight_unit = 'kg'
        self.user.userprofile.save()
        self.assertContains(self.client.get(self.url), 'Speed (km/h)')
