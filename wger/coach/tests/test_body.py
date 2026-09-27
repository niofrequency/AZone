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

# wger
from wger.coach import charts
from wger.coach.body import (
    VTAPER_CATEGORY_NAME,
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
from wger.coach.models import CoachGoal
from wger.core.tests.base_testcase import WgerTestCase
from wger.measurements.models import (
    Category,
    Measurement,
)
from wger.measurements.models.measurement import MeasurementSource


class BodyTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('lifter', password='lifter-password')
        self.user.userprofile.weight_unit = 'lb'
        self.user.userprofile.save()
        self.day = datetime.date(2026, 9, 20)

    def check_in(self, date, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            save_check_in(self.user, CheckIn(date=date, **kwargs))

    def test_categories_created_once(self):
        first = body_categories(self.user)
        second = body_categories(self.user)

        self.assertEqual({k: c.pk for k, c in first.items()}, {k: c.pk for k, c in second.items()})
        self.assertEqual(first['waist'].unit, 'in')
        self.assertEqual(vtaper_category(self.user).pk, vtaper_category(self.user).pk)

    def test_save_check_in(self):
        self.check_in(
            self.day,
            weight=Decimal('178.4'),
            parts={'waist': Decimal('34.5'), 'shoulders': Decimal('48'), 'chest': None},
        )

        self.assertEqual(weight_series(self.user), [Point(self.day, Decimal('178.4'))])
        waist = Category.objects.get(user=self.user, name='Waist')
        self.assertEqual(category_series(self.user, waist), [Point(self.day, Decimal('34.5'))])
        self.assertFalse(Measurement.objects.filter(category__name='Chest').exists())

    def test_second_check_in_on_a_day_corrects_the_first(self):
        self.check_in(self.day, weight=Decimal(180), parts={'waist': Decimal(35)})
        self.check_in(self.day, weight=Decimal(179), parts={'waist': Decimal('34.8')})

        self.assertEqual(weight_series(self.user), [Point(self.day, Decimal(179))])
        waist = Category.objects.get(user=self.user, name='Waist')
        self.assertEqual(Measurement.objects.filter(category=waist).count(), 1)

    def test_shoulder_waist_ratio(self):
        self.check_in(self.day, parts={'waist': Decimal(32), 'shoulders': Decimal(48)})

        ratio = category_series(self.user, vtaper_category(self.user))
        self.assertEqual(ratio, [Point(self.day, Decimal('1.5'))])

    def test_ratio_pairs_close_dates_only(self):
        self.check_in(self.day, parts={'waist': Decimal(32)})
        self.check_in(self.day + datetime.timedelta(days=2), parts={'shoulders': Decimal(48)})
        self.check_in(self.day + datetime.timedelta(days=10), parts={'shoulders': Decimal(49)})

        ratio = category_series(self.user, vtaper_category(self.user))
        self.assertEqual(ratio, [Point(self.day + datetime.timedelta(days=2), Decimal('1.5'))])

    def test_ratio_updates_when_waist_changes(self):
        self.check_in(self.day, parts={'waist': Decimal(32), 'shoulders': Decimal(48)})
        self.check_in(self.day, parts={'waist': Decimal(30)})

        ratio = category_series(self.user, vtaper_category(self.user))
        self.assertEqual(ratio, [Point(self.day, Decimal('1.6'))])
        self.assertEqual(
            Measurement.objects.filter(
                category__name=VTAPER_CATEGORY_NAME, source=MeasurementSource.CALCULATED
            ).count(),
            1,
        )

    def test_history(self):
        self.check_in(self.day, weight=Decimal(180), parts={'waist': Decimal(32)})
        self.check_in(
            self.day + datetime.timedelta(days=7),
            weight=Decimal(178),
            parts={'waist': Decimal(31), 'shoulders': Decimal('49.6')},
        )

        history = check_in_history(self.user)
        self.assertEqual(
            [row['date'] for row in history], [self.day + datetime.timedelta(7), self.day]
        )
        self.assertEqual(history[0]['ratio'], Decimal('1.6'))
        self.assertNotIn('ratio', history[1])

    def test_moving_average(self):
        points = [
            Point(self.day + datetime.timedelta(days=i), Decimal(v))
            for i, v in enumerate([180, 178, 179, 177, 176, 178, 175, 170])
        ]
        averages = moving_average(points)

        self.assertEqual(averages[0].value, 180)
        self.assertEqual(averages[1].value, 179)
        # Day 8 averages days 2-8
        self.assertEqual(averages[7].value, Decimal(1233) / 7)


class GoalModelTestCase(WgerTestCase):
    def test_planned_weight(self):
        user = User.objects.create_user('lifter')
        goal = CoachGoal(
            user=user,
            start_date=datetime.date(2026, 9, 1),
            start_weight=Decimal(180),
            target_weight=Decimal(166),
            target_date=datetime.date(2026, 9, 29),
        )

        self.assertEqual(goal.planned_weight(datetime.date(2026, 9, 15)), Decimal(173))
        self.assertEqual(goal.planned_weight(datetime.date(2026, 8, 1)), Decimal(180))
        self.assertEqual(goal.planned_weight(datetime.date(2026, 12, 1)), Decimal(166))
        self.assertTrue(goal.is_cut)
        self.assertEqual(goal.weeks, 4)


class ChartTestCase(WgerTestCase):
    def test_empty_chart(self):
        chart = charts.build(charts.Chart(id='c', title='T', unit='lb', series=[]))

        self.assertTrue(chart.is_empty)
        self.assertEqual(chart.paths, [])

    def test_chart_geometry(self):
        day = datetime.date(2026, 9, 1)
        points = [Point(day + datetime.timedelta(days=i), Decimal(180 - i)) for i in range(8)]
        chart = charts.build(
            charts.Chart(
                id='c',
                title='T',
                unit='lb',
                series=[
                    charts.Series('daily', 'Daily', points, style='dots'),
                    charts.Series('avg', 'Average', points),
                ],
            )
        )

        self.assertEqual(len(chart.dots), 8)
        self.assertEqual(len(chart.paths), 1)
        self.assertEqual(chart.end_label['label'], '173.0 lb')
        self.assertEqual([t['label'] for t in chart.y_ticks], ['172', '174', '176', '178', '180'])
        # The line spans the plot area from left to right
        self.assertEqual(chart.dots[0]['x'], chart.plot_left)
        self.assertEqual(chart.dots[-1]['x'], chart.plot_right)
        self.assertEqual(len(chart.hover), 8)
        self.assertEqual(len(chart.legend), 2)

    def test_nice_steps(self):
        self.assertEqual(charts.nice_step(8), 2)
        self.assertEqual(charts.nice_step(0.3), 0.1)
        self.assertEqual(charts.nice_step(15), 5)
