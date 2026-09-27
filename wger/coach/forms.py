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
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

# wger
from wger.coach.body import BODY_PARTS
from wger.coach.models import (
    CardioKind,
    CardioTiming,
    CoachGoal,
    FocusArea,
)
from wger.utils.images import validate_image_static_no_animation


class DateInput(forms.DateInput):
    input_type = 'date'


BODY_WEIGHT_RANGE = {'lb': (Decimal(66), Decimal(660)), 'kg': (Decimal(30), Decimal(300))}
LENGTH_RANGE = {'in': (Decimal(5), Decimal(120)), 'cm': (Decimal(10), Decimal(300))}


class GoalForm(forms.ModelForm):
    focus = forms.MultipleChoiceField(
        choices=FocusArea.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Focus areas',
        help_text='These get extra weekly sets when the coach sees them lagging',
    )

    class Meta:
        model = CoachGoal
        fields = [
            'start_date',
            'start_weight',
            'target_weight',
            'target_date',
            'rate_min_per_week',
            'rate_max_per_week',
            'protein_target',
            'step_target',
            'focus',
        ]
        widgets = {
            'start_date': DateInput(),
            'target_date': DateInput(),
        }

    def __init__(self, *args, unit='lb', **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('start_weight', 'target_weight', 'rate_min_per_week', 'rate_max_per_week'):
            self.fields[name].label = f'{self.fields[name].label} ({unit})'

    def clean(self):
        data = super().clean()
        start, target = data.get('start_date'), data.get('target_date')
        if start and target and target <= start:
            self.add_error('target_date', 'The target date has to be after the start date')
        low, high = data.get('rate_min_per_week'), data.get('rate_max_per_week')
        if low is not None and high is not None and low > high:
            self.add_error('rate_max_per_week', 'Has to be at least the slowest weekly change')
        return data


class CheckInForm(forms.Form):
    date = forms.DateField(widget=DateInput(), initial=datetime.date.today)
    weight = forms.DecimalField(
        required=False,
        max_digits=5,
        decimal_places=1,
        label='Body weight',
    )
    photo = forms.ImageField(
        required=False,
        validators=[validate_image_static_no_animation],
        help_text='Optional progress photo, saved to your gallery (PNG or JPEG)',
    )
    notes = forms.CharField(required=False, max_length=500, widget=forms.Textarea({'rows': 2}))

    def __init__(self, *args, weight_unit='lb', length_unit='in', **kwargs):
        super().__init__(*args, **kwargs)
        self.weight_unit = weight_unit
        self.length_unit = length_unit
        self.fields['weight'].label = f'Body weight ({weight_unit})'

        # One field per body part, after the weight
        fields = dict(self.fields)
        self.fields.clear()
        for name in ('date', 'weight'):
            self.fields[name] = fields.pop(name)
        for part in BODY_PARTS:
            self.fields[part.key] = forms.DecimalField(
                required=False,
                max_digits=5,
                decimal_places=1,
                label=f'{part.name} ({length_unit})',
            )
        self.fields.update(fields)

    @property
    def part_keys(self):
        return [part.key for part in BODY_PARTS]

    def clean_date(self):
        date = self.cleaned_data['date']
        if date > timezone.localdate() + datetime.timedelta(days=1):
            raise ValidationError('A check-in cannot be in the future')
        return date

    def clean_weight(self):
        weight = self.cleaned_data.get('weight')
        low, high = BODY_WEIGHT_RANGE[self.weight_unit]
        if weight is not None and not low <= weight <= high:
            raise ValidationError(f'Enter a weight between {low} and {high} {self.weight_unit}')
        return weight

    def clean(self):
        data = super().clean()
        low, high = LENGTH_RANGE.get(self.length_unit, (Decimal(1), Decimal(300)))
        for key in self.part_keys:
            value = data.get(key)
            if value is not None and not low <= value <= high:
                self.add_error(key, f'Enter a value between {low} and {high} {self.length_unit}')

        values = [data.get('weight'), data.get('photo'), *(data.get(k) for k in self.part_keys)]
        if not self.errors and all(v in (None, '') for v in values):
            raise ValidationError('Enter at least one value or a photo')
        return data


class ActivityForm(forms.Form):
    """
    A day's steps and/or one cardio session
    """

    date = forms.DateField(widget=DateInput(), initial=datetime.date.today)
    steps = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=100000,
        help_text='Total for the day, from your phone or watch',
    )
    kind = forms.ChoiceField(
        label='Cardio',
        choices=CardioKind.choices,
        initial=CardioKind.INCLINE_WALK,
    )
    timing = forms.ChoiceField(label='When', choices=CardioTiming.choices)
    duration = forms.IntegerField(
        label='Duration (min)',
        required=False,
        min_value=1,
        max_value=600,
    )
    incline = forms.DecimalField(
        label='Incline (%)',
        required=False,
        min_value=0,
        max_value=40,
        max_digits=3,
        decimal_places=1,
    )
    speed = forms.DecimalField(
        required=False,
        min_value=0,
        max_value=50,
        max_digits=4,
        decimal_places=1,
    )
    notes = forms.CharField(required=False, max_length=200)

    def __init__(self, *args, speed_unit='mph', **kwargs):
        super().__init__(*args, **kwargs)
        self.speed_unit = speed_unit
        self.fields['speed'].label = f'Speed ({"mph" if speed_unit == "mph" else "km/h"})'

    def clean_date(self):
        date = self.cleaned_data['date']
        if date > timezone.localdate() + datetime.timedelta(days=1):
            raise ValidationError('Activity cannot be in the future')
        return date

    def clean(self):
        data = super().clean()
        if not self.errors and data.get('steps') is None and data.get('duration') is None:
            raise ValidationError('Enter your steps, a cardio duration, or both')
        return data
