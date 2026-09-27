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
from decimal import (
    Decimal,
    InvalidOperation,
)

# Django
from django.contrib.auth.models import User
from django.core.management.base import (
    BaseCommand,
    CommandError,
)

# wger
from wger.coach.programs.aesthetic165 import PROGRAM
from wger.coach.seed import (
    ProgramError,
    seed_program,
)


class Command(BaseCommand):
    """
    Sets up the "Aesthetic 165" routine, nutrition plan and body measurements
    for a user
    """

    help = (
        'Creates the "Aesthetic 165" upper/lower routine, nutrition goals, meals '
        'and body measurement categories for an existing user.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--user', required=True, help='Username to set the program up for')
        parser.add_argument(
            '--start',
            help='First day of the routine as YYYY-MM-DD (default: today)',
        )
        parser.add_argument(
            '--current-weight',
            help="Log this as today's body weight, e.g. 179",
        )
        parser.add_argument(
            '--unit',
            choices=['lb', 'kg'],
            default='lb',
            help='Weight unit for the profile and all exercises (default: lb)',
        )
        parser.add_argument(
            '--replace',
            action='store_true',
            help=(
                'Recreate the routine if the program was already set up and update the '
                'nutrition goals. Logged workouts and meals are kept.'
            ),
        )

    def handle(self, **options):
        try:
            user = User.objects.get(username=options['user'])
        except User.DoesNotExist:
            raise CommandError(f'User "{options["user"]}" does not exist. Sign up first.')

        start = None
        if options['start']:
            try:
                start = datetime.date.fromisoformat(options['start'])
            except ValueError:
                raise CommandError('--start must be a date like 2026-09-28')

        current_weight = None
        if options['current_weight']:
            try:
                current_weight = Decimal(options['current_weight'])
            except InvalidOperation:
                raise CommandError('--current-weight must be a number, e.g. 179')

        try:
            result = seed_program(
                user,
                PROGRAM,
                start=start,
                current_weight=current_weight,
                weight_unit=options['unit'],
                replace=options['replace'],
            )
        except ProgramError as e:
            raise CommandError(str(e))

        routine = result.routine
        self.stdout.write(self.style.SUCCESS(f'"{PROGRAM.name}" is set up for {user.username}'))
        self.stdout.write(f'  Routine:   {routine.name} ({routine.start} to {routine.end})')
        for day in routine.days.all():
            if day.is_rest:
                self.stdout.write(f'    - {day.name}')
            else:
                self.stdout.write(f'    - {day.name}: {day.slots.count()} exercises')
        plan = result.plan
        self.stdout.write(
            f'  Nutrition: {plan.goal_energy} kcal, {plan.goal_protein} g protein, '
            f'{plan.goal_carbohydrates} g carbs, {plan.goal_fat} g fat'
        )
        self.stdout.write(f'  Meals:     {", ".join(m.name for m in plan.meal_set.all())}')
        self.stdout.write(f'  Measure:   {", ".join(c.name for c in result.categories)}')
        if result.body_weight:
            self.stdout.write(f'  Weight:    {result.body_weight.value} {options["unit"]} logged')
