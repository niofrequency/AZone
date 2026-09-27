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
Double progression for wger slot entries.

Every exercise has a rep range (e.g. 4 x 8-10). The targets for the next
session are derived from what was actually logged in the previous one:

* all sets reached the top of the range -> add weight, go back to the bottom
* all sets reached the current rep target -> same weight, one more rep
* otherwise -> same targets again

Three sessions in a row without progress at the same weight trigger a deload
(-10% weight, bottom of the range), after which the cycle starts again.

Enabled per exercise with ``SlotEntry.class_name = 'double_progression'``.
Optional settings in ``SlotEntry.config``:

* ``increment``: weight added when the top of the range is reached
  (default 5 for lb, 2.5 for kg)
* ``deload_after``: sessions without progress before a deload (default 3)
* ``deload_percent``: how much the weight drops on a deload (default 10)
"""

# Standard Library
from collections import (
    Counter,
    defaultdict,
)
from dataclasses import dataclass
from decimal import (
    ROUND_DOWN,
    Decimal,
)

# wger
from wger.manager.config_calculations.calculations import AbstractSetCalculations
from wger.manager.consts import (
    WEIGHT_UNIT_KG,
    WEIGHT_UNIT_LB,
)
from wger.manager.dataclasses import (
    SetConfigData,
    round_value,
)


LB_PER_KG = Decimal('2.20462')

DEFAULT_INCREMENT = {WEIGHT_UNIT_LB: Decimal(5), WEIGHT_UNIT_KG: Decimal('2.5')}
DEFAULT_DELOAD_AFTER = 3
DEFAULT_DELOAD_PERCENT = 10


@dataclass
class ProgressionState:
    weight: Decimal | None
    """Target weight, None until a weight was given or logged"""

    repetitions: int
    """Current rep target, between the bottom and the top of the range"""

    sessions_without_progress: int = 0
    last_total_reps: int | None = None
    last_weight: Decimal | None = None
    """Weight of the last session, progress is only compared at the same weight"""

    deload: bool = False
    """The current iteration is a deload"""


def latest_value(configs, default=None):
    """
    Value of the config with the highest iteration, i.e. the one in effect
    """
    configs = sorted(configs, key=lambda c: c.iteration)
    return configs[-1].value if configs else default


class DoubleProgression(AbstractSetCalculations):
    def calculate(self) -> SetConfigData:
        entry = self.slot_entry
        options = (entry.config if entry is not None else None) or {}

        self.unit = entry.weight_unit_id if entry is not None else WEIGHT_UNIT_KG
        self.sets = int(latest_value(self.sets_configs, 1))
        self.reps_min = int(latest_value(self.repetition_configs, 1))
        self.reps_max = int(latest_value(self.max_repetition_configs, self.reps_min))
        self.reps_max = max(self.reps_max, self.reps_min)
        self.increment = Decimal(
            str(options.get('increment', DEFAULT_INCREMENT.get(self.unit, Decimal('2.5'))))
        )
        self.deload_after = int(options.get('deload_after', DEFAULT_DELOAD_AFTER))
        deload_percent = Decimal(options.get('deload_percent', DEFAULT_DELOAD_PERCENT))
        self.deload_factor = 1 - deload_percent / 100
        self.rounding = (
            Decimal(entry.weight_rounding)
            if entry is not None and entry.weight_rounding
            else self.increment / 2
        )

        state = self.walk(max(self.iteration, 1))
        return self.to_config_data(state)

    def walk(self, iteration: int) -> ProgressionState:
        """
        Replays every logged session up to the requested iteration
        """
        start_weight = latest_value(self.weight_configs)
        state = ProgressionState(
            weight=Decimal(start_weight) if start_weight is not None else None,
            repetitions=self.reps_min,
        )

        logs_by_iteration = defaultdict(list)
        for log in self.logs:
            if log.repetitions is not None:
                logs_by_iteration[log.iteration].append(log)

        for i in range(2, iteration + 1):
            logs = logs_by_iteration.get(i - 1)
            state.deload = False
            if logs:
                self.advance(state, logs)
        return state

    def advance(self, state: ProgressionState, logs) -> None:
        """
        Sets the targets for the next session from the logs of the previous one
        """
        weight = self.working_weight(logs)
        if weight is not None:
            # Follow what was actually lifted, e.g. when a heavier weight was used
            state.weight = weight

        def done_at_weight(log) -> bool:
            if weight is None:
                return True
            logged = self.logged_weight(log)
            return logged is not None and logged >= weight

        working_sets = [log for log in logs if done_at_weight(log)]
        reps = [int(log.repetitions) for log in working_sets]
        sets_at_top = sum(1 for r in reps if r >= self.reps_max)
        sets_at_target = sum(1 for r in reps if r >= state.repetitions)
        total_reps = sum(reps)

        if sets_at_top >= self.sets and state.weight is not None:
            state.weight += self.increment
            state.repetitions = self.reps_min
            state.sessions_without_progress = 0
            state.last_total_reps = None
            return

        if sets_at_target >= self.sets:
            state.repetitions = min(state.repetitions + 1, self.reps_max)

        no_progress = (
            state.last_weight == state.weight
            and state.last_total_reps is not None
            and total_reps <= state.last_total_reps
        )
        if no_progress:
            state.sessions_without_progress += 1
        else:
            state.sessions_without_progress = 0
        state.last_total_reps = total_reps
        state.last_weight = state.weight

        if state.sessions_without_progress >= self.deload_after - 1 and state.weight:
            state.weight = self.round_down(state.weight * self.deload_factor)
            state.repetitions = self.reps_min
            state.sessions_without_progress = 0
            state.last_total_reps = None
            state.deload = True

    def working_weight(self, logs) -> Decimal | None:
        """
        The weight most sets were done with, the heavier one on a tie
        """
        weights = [w for w in (self.logged_weight(log) for log in logs) if w is not None]
        if not weights:
            return None
        counts = Counter(weights)
        return max(counts, key=lambda w: (counts[w], w))

    def logged_weight(self, log) -> Decimal | None:
        """
        The logged weight, converted to the unit of the exercise if needed
        """
        if log.weight is None:
            return None
        weight = Decimal(log.weight)
        if log.weight_unit_id == WEIGHT_UNIT_KG and self.unit == WEIGHT_UNIT_LB:
            return self.round_nearest(weight * LB_PER_KG)
        if log.weight_unit_id == WEIGHT_UNIT_LB and self.unit == WEIGHT_UNIT_KG:
            return self.round_nearest(weight / LB_PER_KG)
        return weight

    def round_down(self, value: Decimal) -> Decimal:
        return (value / self.rounding).to_integral_value(ROUND_DOWN) * self.rounding

    def round_nearest(self, value: Decimal) -> Decimal:
        return (value / self.rounding).to_integral_value() * self.rounding

    def to_config_data(self, state: ProgressionState) -> SetConfigData:
        entry = self.slot_entry
        comment = entry.comment if entry is not None else ''
        if state.deload:
            note = 'Deload: lighter week after 3 sessions without progress'
            comment = f'{comment} · {note}' if comment else note

        has_weight = state.weight is not None
        return SetConfigData(
            slot_entry_id=entry.id if entry is not None else None,
            exercise=entry.exercise_id if entry is not None else None,
            type=str(entry.type) if entry is not None else 'normal',
            comment=comment,
            sets=self.sets,
            weight=round_value(state.weight, self.rounding) if has_weight else None,
            weight_unit=self.unit if has_weight else None,
            weight_unit_name=entry.weight_unit.name
            if has_weight and entry is not None and entry.weight_unit
            else None,
            weight_rounding=entry.weight_rounding if has_weight and entry is not None else None,
            repetitions=state.repetitions,
            max_repetitions=self.reps_max if self.reps_max > state.repetitions else None,
            repetitions_unit=entry.repetition_unit_id if entry is not None else None,
            repetitions_unit_name=entry.repetition_unit.name
            if entry is not None and entry.repetition_unit
            else None,
            repetitions_rounding=entry.repetition_rounding if entry is not None else None,
            rir=latest_value(self.rir_configs),
            rest=latest_value(self.rest_configs),
        )
