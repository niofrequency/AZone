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
Building blocks used to describe a training + nutrition program as data
"""

# Standard Library
import datetime
from dataclasses import (
    dataclass,
    field,
)


@dataclass(frozen=True)
class ExerciseSpec:
    uuid: str
    """UUID of the exercise in wger's exercise database"""

    name: str
    """Display name, only used for messages. The exercise's own name is shown in the app"""

    target: str
    sets: int
    reps_min: int
    reps_max: int
    rir: int
    """Target reps in reserve. RPE = 10 - RIR"""

    rest: int
    """Rest between sets, in seconds"""

    notes: str = ''
    """Form and technique notes, shown next to the exercise"""

    increment_lb: float = 5
    """
    Weight added once every set reaches the top of the rep range. Halved when
    the program is set up in kg
    """


@dataclass(frozen=True)
class DaySpec:
    name: str
    description: str
    exercises: list[ExerciseSpec]


@dataclass(frozen=True)
class MealSpec:
    name: str
    time: datetime.time | None = None


@dataclass(frozen=True)
class NutritionSpec:
    description: str
    energy: int
    protein: int
    carbohydrates: int
    fat: int
    fiber: int | None = None
    meals: list[MealSpec] = field(default_factory=list)


@dataclass(frozen=True)
class MeasurementSpec:
    name: str
    unit: str
    metric_type: str = 'custom'


@dataclass(frozen=True)
class ProgramSpec:
    name: str
    description: str
    weeks: int
    days: list[DaySpec]
    nutrition: NutritionSpec
    rest_days_after_cycle: int = 0
    """Rest days appended after the training days before the cycle repeats"""

    measurements: list[MeasurementSpec] = field(default_factory=list)
