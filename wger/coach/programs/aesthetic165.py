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
The "Aesthetic 165" program: a 10-12 week cut from 179 to 165 lb that
prioritises upper chest, lat width, shoulder caps and a leaner midsection.

Everything here is plain data so it can be edited without touching the seeding
logic. Exercises are referenced by the UUIDs of wger's exercise database, which
are stable across installations.
"""

# Standard Library
import datetime

# wger
from wger.coach.programs.base import (
    DaySpec,
    ExerciseSpec,
    GoalSpec,
    MealSpec,
    MeasurementSpec,
    NutritionSpec,
    ProgramSpec,
)


UPPER_A = DaySpec(
    name='Upper A',
    description='Chest / back width / shoulders focus',
    exercises=[
        ExerciseSpec(
            uuid='11f5de05-7709-484f-b7d9-d9a8af57b5b7',
            name='Incline Dumbbell Press (30°)',
            target='Upper chest / armpit tie-in',
            sets=4,
            reps_min=8,
            reps_max=10,
            rir=2,
            rest=120,
            notes='Deep stretch at the bottom; drive elbows slightly inward on the way up.',
        ),
        ExerciseSpec(
            uuid='c6daf781-02ba-4b73-8e88-530165afd32d',
            name='Wide-Grip Lat Pulldown',
            target='Lat width (V-taper)',
            sets=4,
            reps_min=8,
            reps_max=12,
            rir=2,
            rest=120,
            notes='Drive elbows down toward the hips; lean back slightly at full contraction.',
            increment_lb=10,
        ),
        ExerciseSpec(
            uuid='09dd3e3c-e53a-4e2c-a2e3-645d334f53e2',
            name='Chest Dips (forward lean)',
            target='Outer chest stretch / lower pecs',
            sets=3,
            reps_min=10,
            reps_max=12,
            rir=2,
            rest=90,
            notes='Lean torso forward; hold the bottom stretch for 1 second.',
        ),
        ExerciseSpec(
            uuid='51a2d520-b510-4b6e-bd65-9fc40365e8de',
            name='Chest-Supported Row',
            target='Upper back / rear delts',
            sets=3,
            reps_min=10,
            reps_max=12,
            rir=1,
            rest=90,
            notes='Retract shoulder blades; squeeze the upper back at peak contraction.',
        ),
        ExerciseSpec(
            uuid='63375f5b-2d81-471c-bea4-fc3d207e96cb',
            name='Lateral Raises (cable or dumbbell)',
            target='Lateral delts (shoulder width)',
            sets=4,
            reps_min=12,
            reps_max=15,
            rir=1,
            rest=60,
            notes='Lift out toward the walls; strict control, no swinging.',
        ),
        ExerciseSpec(
            uuid='fc608f0e-d754-4911-ae59-8856952e7064',
            name='Tricep Rope Pushdowns',
            target='Triceps (lateral & long head)',
            sets=3,
            reps_min=12,
            reps_max=15,
            rir=1,
            rest=60,
            notes='Lock elbows at your sides; spread the rope at the bottom.',
        ),
    ],
)

LOWER_B = DaySpec(
    name='Lower B',
    description='Quad sweep / hamstrings / calves focus',
    exercises=[
        ExerciseSpec(
            uuid='f462df26-3264-48c2-b5aa-2374d0670c24',
            name='Hack Squat',
            target='Quad sweep & vastus medialis',
            sets=4,
            reps_min=8,
            reps_max=10,
            rir=2,
            rest=150,
            notes='Feet low on the platform; drive knees forward over toes for quad bias.',
            increment_lb=10,
        ),
        ExerciseSpec(
            uuid='440a5184-de58-4a86-a7ba-76ddeafaa855',
            name='Seated Leg Curl',
            target='Hamstrings',
            sets=4,
            reps_min=10,
            reps_max=12,
            rir=1,
            rest=90,
            notes='Squeeze hamstrings hard at the bottom; 2-second negative.',
            increment_lb=10,
        ),
        ExerciseSpec(
            uuid='66a42396-c207-44da-bc75-758a89d32404',
            name='Leg Press',
            target='Overall quad & leg mass',
            sets=3,
            reps_min=10,
            reps_max=12,
            rir=2,
            rest=120,
            notes='Controlled descent; keep the lower back flat against the pad.',
            increment_lb=20,
        ),
        ExerciseSpec(
            uuid='62170477-90ec-463c-907e-9e523abc0a15',
            name='Leg Extension',
            target='Quad separation',
            sets=3,
            reps_min=12,
            reps_max=15,
            rir=1,
            rest=60,
            notes='Hold a 1-second squeeze at peak extension.',
            increment_lb=10,
        ),
        ExerciseSpec(
            uuid='7ce443b6-eb84-4f65-b05f-461c1cc8bcc0',
            name='Standing Calf Raises',
            target='Calves',
            sets=4,
            reps_min=12,
            reps_max=15,
            rir=1,
            rest=60,
            notes='Pause 2 seconds in the bottom stretch before raising up.',
            increment_lb=10,
        ),
    ],
)

PROGRAM = ProgramSpec(
    name='Aesthetic 165',
    description=(
        'Upper/lower split on a 3-day cycle (Upper A, Lower B, rest), which works out '
        'to 4-5 sessions a week. Goal: 179 -> 165 lb at 1.0-1.5 lb/week while keeping '
        'upper chest, lats and delts. Cardio: 30-45 min incline walk (10-12%, '
        '3.0-3.5 mph) and 8,000-10,000 steps daily.'
    ),
    weeks=12,
    days=[UPPER_A, LOWER_B],
    rest_days_after_cycle=1,
    nutrition=NutritionSpec(
        description='Aesthetic 165 - cut',
        energy=1900,
        protein=165,
        carbohydrates=165,
        fat=52,
        fiber=30,
        meals=[
            MealSpec(
                name='Breakfast',
                time=datetime.time(8, 0),
            ),
            MealSpec(
                name='Lunch',
                time=datetime.time(12, 30),
            ),
            MealSpec(
                name='Pre-workout',
                time=datetime.time(16, 0),
            ),
            MealSpec(
                name='Dinner',
                time=datetime.time(19, 30),
            ),
        ],
    ),
    measurements=[
        MeasurementSpec(name='Steps', unit='', metric_type='steps'),
    ],
    goal=GoalSpec(
        target_weight_lb=165,
        rate_min_per_week_lb=1.0,
        rate_max_per_week_lb=1.5,
        protein=165,
        steps=10000,
        focus=['upper_chest', 'lats', 'side_delts', 'abs'],
    ),
)
