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

# Django
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

# wger
from wger.coach.rules import run_rules


class Command(BaseCommand):
    """
    Refreshes the coach recommendations, e.g. from a nightly cron job. The
    dashboard also refreshes them whenever it is opened
    """

    help = 'Runs the coach rules for every user with a goal, or for one user'

    def add_arguments(self, parser):
        parser.add_argument('--user', help='Only this username')

    def handle(self, **options):
        users = User.objects.filter(coach_goal__isnull=False)
        if options['user']:
            users = User.objects.filter(username=options['user'])
        for user in users:
            pending = run_rules(user)
            self.stdout.write(f'{user.username}: {len(pending)} recommendations')
