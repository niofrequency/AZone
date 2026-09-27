# AZone: Building "Aesthetic 165" on a wger fork

**Decision:** fork [wger](https://github.com/wger-project/wger) (Django, AGPL-3.0) and ship it as a **web app**.
Add one new Django app, `wger.coach`, that holds everything your PRD needs and wger doesn't have:
the "update my body and it tells me what to fix and adjusts my exercises" engine.

This plan was written against wger `master` as of 2026-09-27 (version `2.6-alpha1`).
File paths below refer to that codebase.

---

## 1. Why wger, and the one rule it comes with

wger already has multiple users with sign-up, workout routines, set/rep/weight/RIR logging, a progression
system, nutrition plans with macro goals, a food database, body measurements (including **steps**),
a progress photo gallery, charts, a REST API and a web UI. Your PRD would take months to build from scratch,
and wger already covers about 70% of it.

**License (AGPL-3.0):** you can use and change it freely. The one obligation is that if other people use
your hosted version, you must make your modified source available to them. The simplest way to handle that
is to keep the AZone fork public. For personal use only, you don't have to do anything.

---

## 2. Where your PRD fits in wger

✅ = already exists, just configure it · 🔧 = exists, needs a small extension · 🆕 = build it in `wger.coach`

### Module A: Dynamic Workout Logger

| PRD requirement | wger piece | Status |
|---|---|---|
| Upper / Lower split, 4–5 days/week | `Routine` → `Day` → `Slot` → `SlotEntry` (`wger/manager/models/`). Seeded as a repeating Upper A → Lower B → Rest cycle (about 4.7 sessions/week) so each exercise has a single progression track | ✅ |
| Exercise list with target muscle | Exercise database with `Muscle` (`wger/exercises/models/muscle.py`) | ✅ all 11 PRD exercises exist (dips use wger's generic "Dips", with the forward-lean cue in the notes) |
| Sets × rep ranges (4×8–10) | `SetsConfig`, `RepetitionsConfig` + `MaxRepetitionsConfig` (a min–max range) | ✅ |
| Form & technique notes | `SlotEntry.comment` / `Slot.comment` | ✅ |
| Log sets, reps, weight | `WorkoutLog` (`wger/manager/models/log.py`) | ✅ |
| RPE | wger stores **RIR** (reps in reserve). RPE = 10 − RIR, and `SetConfigData.rpe` already converts it | ✅ |
| Week-over-week progression indicator | Logs store `weight_target` / `repetitions_target` alongside actual values, so the delta is already there | ✅ "Last session vs. the one before" on the coach dashboard |
| Automatic progression | Rule-based `WeightConfig` etc. (for example "+5 lb every iteration if all reps hit"), **or** a custom Python class through `SlotEntry.class_name` → `wger/manager/config_calculations/` | ✅ `double_progression` (§4.2) |

### Module B: Nutrition & Protein

| PRD requirement | wger piece | Status |
|---|---|---|
| Protein 150–175 g, ~1,800–2,000 kcal, carbs, fat | `NutritionPlan.goal_protein / goal_energy / goal_carbohydrates / goal_fat` (`wger/nutrition/models/plan.py`) | ✅ |
| Meal logger | `LogItem` + Open Food Facts ingredient DB | ✅ |
| Meal pre-sets (Breakfast / Lunch / Pre-WO / Dinner) | `Meal` + `MealItem` inside a plan. You can log a whole planned meal in one tap | ✅ create your 4 meals once |
| Deficit that adapts to your real weight trend | Not present | ✅ weight trend rule + "Apply" changes the calorie goal (§4.3) |

### Module C: Cardio / NEAT

| PRD requirement | wger piece | Status |
|---|---|---|
| Daily steps (8k–10k) | Measurements with `MetricType.STEPS` (`wger/measurements/models/category.py`) | ✅ |
| Incline walk: incline %, speed, duration | No cardio model. wger's workout log only has reps/weight | ✅ `CardioSession` model in `wger.coach` |

### Body tracking (what powers the "tell me what to fix" part)

| PRD requirement | wger piece | Status |
|---|---|---|
| Body weight (179 → 165) | `MetricType.BODY_WEIGHT` measurements | ✅ |
| Waist, chest, shoulders, arms, thighs | Custom measurement categories | ✅ create them |
| Progress photos | `wger.gallery` | ✅ |
| Shoulder-to-waist ratio (V-taper) | Pluggable "dynamic measurements" (`wger/measurements/dynamic/types.py` already has BMI, waist-to-height, 1RM) | ✅ `SHOULDER_WAIST` type in `wger/coach/dynamic.py` |
| Target weight / goal date | `UserProfile` has height, age and activity but **no goal** | ✅ `CoachGoal` model |

### Data schema (PRD §6)

Your JSON maps onto existing tables, so there's no need for a new schema:
`user_profile` → `UserProfile` + `CoachGoal` · `daily_log.weight` → `Measurement` (body_weight) ·
`cardio_completed` → `CardioSession` · `workouts[].exercises[].sets[]` → `WorkoutSession` + `WorkoutLog` rows ·
`nutrition` → `LogItem`s summed per day.

---

## 3. What doesn't fit, and what to do about it

- **Cardio details (incline %, speed).** wger has nowhere to store these, so we add our own small model instead of forcing them into `WorkoutLog`.
- **The React web UI lives in a different repo** ([`wger-project/react`](https://github.com/wger-project/react), shipped as the npm package `@wger-project/react-components`). **Don't fork it.** Build the coach pages with Django templates + **htmx**, which wger already depends on (`package.json`). You avoid maintaining a second repo, and the new pages sit inside wger's normal layout (`wger/core/templates/template.html`).
- **Mobile app** (Flutter) is out of scope. The site works in a phone browser, and wger's official app will still show your routines and logs because we only *add* tables.

---

## 4. The new `wger/coach` app

```
wger/coach/
├── apps.py, urls.py, admin.py
├── models.py            # CoachGoal, CardioSession, Recommendation
├── rules/               # the engine: one small file per rule
│   ├── base.py          # Rule interface + registry (same pattern as wger/trophies/checkers/registry.py)
│   ├── weight_trend.py
│   ├── v_taper.py
│   ├── stalled_lift.py
│   ├── muscle_balance.py
│   └── protein.py
├── services.py          # run_all_rules(user) -> list[Recommendation]
├── signals.py           # rerun on new Measurement / WorkoutLog (like wger/trophies/signals.py)
├── tasks.py             # nightly Celery job (wger already runs Celery)
├── management/commands/seed_aesthetic165.py
├── templates/coach/     # dashboard, check-in form, cardio form (htmx)
└── tests/
```

Register it in `settings/settings_global.py` → `INSTALLED_APPS` next to `'wger.trophies'`.

### 4.1 Models

```python
class CoachGoal(models.Model):
    user            = OneToOneField(User)
    target_weight   = DecimalField()          # 165
    target_date     = DateField()             # start + 12 weeks
    rate_min_per_wk = DecimalField(default=1.0)
    rate_max_per_wk = DecimalField(default=1.5)
    protein_g_per_lb_goal = DecimalField(default=1.0)   # 165 lb → 165 g
    step_target     = IntegerField(default=10000)
    focus           = JSONField(default=list) # ["upper_chest", "lats", "side_delts", "abs"]

class CardioSession(models.Model):
    user, date, kind ("incline_walk", "treadmill", "outdoor")
    duration_min, incline_pct, speed_mph, notes

class Recommendation(models.Model):
    user, created, rule_slug, severity ("info" | "adjust" | "warning")
    title, body          # "Lateral delts lagging: +1 set of lateral raises"
    action = JSONField() # machine-readable change, e.g. {"slot_entry": 42, "sets": "+1"}
    status ("pending" | "applied" | "dismissed")
```

Because targets are stored per user (`CoachGoal`) and not hard-coded, **anyone can sign up**, enter their
own weight and goal, and get their own targets. Your PRD values are just the defaults in the seed command.

### 4.2 Progression: `double_progression` ✅

wger lets any `SlotEntry` hand its progression logic to a Python class (`SlotEntry.class_name`).
The seed command sets `class_name = "double_progression"` on every exercise. The entry point is
`wger/manager/config_calculations/double_progression.py`, and the logic is in `wger/coach/progression.py`.

For each session, the targets come from what was logged in the previous session of that day:
1. **Every set reached the top of the rep range** (for example 4 × 10 on 8–10): add weight and go back to
   the bottom of the range. The increment is per exercise in `SlotEntry.config`: +5 lb for dumbbells and
   cables, +10 lb for most machines, +20 lb for leg press. It's halved in kg.
2. **Every set reached the current rep target:** same weight, aim for one more rep (8–10 → 9–10 → 10).
3. **Otherwise** the same targets again.
4. **Three sessions in a row without more total reps at the same weight:** a one-session deload
   (−10% weight, bottom of the range, with a "Deload" note on the exercise).

It follows the weight you actually used (the weight most sets were done with). kg logs are converted
for lb exercises. Body-weight exercises with no weight logged progress by reps only.

Two small changes to wger itself make this possible. Custom classes now get the `slot_entry` (to read
its config), and only the routine owner's logs, the same user filter wger's built-in rules already use.

The class returns `SetConfigData(...)`, so wger's routine view, table, gym mode, API and mobile app all
show the new targets with no other changes.

### 4.3 Rules engine: "what to fix"

Each rule reads existing wger data and outputs `Recommendation`s. Rules marked **auto** also apply the change
when the user taps "Apply".

| Rule | Reads | Trigger → output |
|---|---|---|
| **Weight trend** | body_weight measurements, 7-day rolling average | Losing < 0.5 lb/wk for 14 days → "Cut 150 kcal *or* +2,000 steps" (**auto**: lowers `NutritionPlan.goal_energy`). Losing > 2 lb/wk → "+150 kcal to protect muscle". On track → ✅ |
| **Protein** | nutrition logs, last 7 days | Average < goal − 15 g → "Protein is short by X g/day", with a pre-set meal suggestion |
| **V-taper** | shoulder & waist measurements → `SHOULDER_WAIST` ratio | Ratio < 1.5 and shoulders flat for 4 weeks → +1 set lateral raises & lat pulldown (**auto**). Waist not going down while weight is → check the protein/deficit rule |
| **Stalled lift** | `WorkoutLog` per exercise | No weight or rep improvement in 3 sessions → swap to a variation (for example Incline DB → Incline Smith) or deload |
| **Muscle balance** | weekly sets per `Muscle` from logs vs. `CoachGoal.focus` | Focus muscle < 10 hard sets/week → add a set. Push:pull sets > 1.3 → add a row set |
| **Steps / cardio** | steps measurement + `CardioSession` | Average steps < 8,000 over 7 days → nudge. Hitting targets → show streak |

"Adjusting the exercises" means changing the `SetsConfig` / `SlotEntry` rows of your routine. It uses wger's
existing tables, so the change shows up everywhere.

### 4.4 Web pages (Django templates + htmx)

- **`/coach/`** is the dashboard. It shows: weight trend vs. goal line, days left, this week's recommendations
  (Apply / Dismiss buttons), protein & calories today, steps, and V-taper ratio.
- **`/coach/check-in/`** is a weekly form: weight, waist, chest, shoulders, arms, photo upload. It saves
  wger `Measurement` + `gallery` entries and reruns the rules.
- **`/coach/cardio/`** is a quick cardio log.
- **`/coach/goal/`** sets up the goal for new users (current → target weight, timeline, focus areas).
- Add a "Coach" item to wger's main navigation.

### 4.5 Seed command: your PRD in one command

`python manage.py seed_aesthetic165 --user <you>` creates:
- the Routine "Aesthetic 165" with **Upper A** (6 exercises) and **Lower B** (5 exercises), your exact sets and
  rep ranges, your form notes as comments, and `double_progression` on every entry
- a Nutrition plan: 165 g protein, 1,900 kcal, 165 g carbs, 52 g fat, plus Breakfast / Lunch / Pre-WO / Dinner meals
- measurement categories: Waist, Chest, Shoulders, Arms, Thighs, Steps, plus the Shoulder:Waist dynamic category
- `CoachGoal(target_weight=165, 12 weeks, focus=[upper_chest, lats, side_delts, abs])`. Comes in milestone 4, together with the model

---

## 5. Getting started

See [getting-started.md](getting-started.md) for running AZone locally and loading the program.

Hosting it for yourself and friends: a small VPS (or Railway/Fly) running wger's docker-compose (Postgres + Redis + Celery).

---

## 6. Milestones

| # | Milestone | Done when | Status |
|---|---|---|---|
| 1 | Fork runs locally | You can sign up, log an Upper A workout, and log a meal | ✅ |
| 2 | Seed command | One command sets up your full PRD routine and nutrition plan | ✅ `seed_aesthetic165` |
| 3 | `double_progression` | Hitting 4×10 on Incline DB gives 4×8 at +5 lb next session | ✅ |
| 4 | Coach models + check-in page | Weekly measurements & photos saved. V-taper ratio charted | ✅ `/coach/check-in/`, `/coach/goal/` |
| 5 | Rules engine + dashboard | Recommendations appear, and "Apply" changes the routine or calorie goal | ✅ `/coach/` |
| 6 | Cardio + steps | Cardio log and 7-day steps average on the dashboard | ✅ `/coach/cardio/` |
| 7 | Deploy | Public URL, other people can sign up and set their own goals | |

Each milestone gets tests in `wger/coach/tests/`, following wger's existing test style.
