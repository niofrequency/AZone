# AZone: getting started

AZone is a fork of [wger](https://github.com/wger-project/wger) with a `wger/coach` app on top
(see [wger-fork-plan.md](wger-fork-plan.md)). This page gets it running on your machine and
loads the "Aesthetic 165" program.

## 1. Run it locally

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js and npm.

```bash
uv sync --group dev                 # Python dependencies (creates .venv)
npm install -g sass                 # CSS compiler used by the build step

export DJANGO_SETTINGS_MODULE=settings.local_dev   # SQLite in ./db, no Postgres/Redis needed
uv run wger bootstrap --settings-path settings.local_dev
uv run python manage.py runserver
```

Open <http://127.0.0.1:8000>. `bootstrap` creates an `admin` user with password `adminadmin`.
Change it, or sign up with your own account under **Register**.

Optional: to search foods when logging meals, load the ingredient database (a large download):

```bash
uv run wger load-online-fixtures --settings-path settings.local_dev
```

## 2. Load the Aesthetic 165 program

```bash
uv run python manage.py seed_aesthetic165 --user <your-username> --current-weight 179
```

This creates:

| What | Details |
|---|---|
| Routine "Aesthetic 165" | 12 weeks, repeating **Upper A → Lower B → Rest** (4–5 sessions/week). Every exercise has its sets, rep range, RIR (RPE = 10 − RIR), rest time and form notes from the PRD, and progresses automatically (see below) |
| Nutrition plan "Aesthetic 165 - cut" | 1,900 kcal · 165 g protein · 165 g carbs · 52 g fat · 30 g fiber, with Breakfast / Lunch / Pre-workout / Dinner meals |
| Measurements | Waist, Chest, Shoulders, Arms, Thighs (inches) and Steps |
| Body weight | Today's weight, if `--current-weight` is given. Your profile is switched to lb |

Options:

- `--start 2026-09-28` sets the first day of the routine (default: today)
- `--unit kg` uses kilograms instead of pounds
- `--replace` rebuilds the routine and updates the nutrition goals if you already ran it. Logged
  workouts and meals are kept

The program itself is plain data in `wger/coach/programs/aesthetic165.py`. Edit exercises, sets or
macros there and run the command again with `--replace`.

Training days wait for you: if you skip a day, the routine doesn't move on until you log that
session, so the exercises keep progressing in order.

## 3. Daily use

Start at **Coach → Dashboard** (`/coach/`). It shows your 7-day average weight, weekly pace, what's
left to go, your V-taper ratio and today's protein and calories, plus:

- **What to work on:** adjustments the coach suggests. Most have a button that makes the change
  for you (lower the calorie goal by 150 kcal, add a set to an exercise). **Dismiss** hides one
  for two weeks.
- **Status:** what's going well and notes to keep in mind.
- **Next workout** and **Last session vs. the one before** (▲ +5 lb, +2 reps).

The coach's rules (`wger/coach/rules/`):

| Rule | Looks at | Suggests |
|---|---|---|
| Weight trend | this week's vs. last week's average weight | cut or add 150 kcal when you're too slow or too fast |
| Nutrition | protein and calories of the last 7 logged days | more protein when you're >15 g short |
| V-taper | shoulder:waist ratio, waist and shoulder trends | more side delt volume if shoulders stall |
| Muscle balance | weekly sets per focus area, push vs. pull | +1 set where a focus muscle gets <10 sets a week, or pulling lags pressing |
| Stalled lifts | the last 3 sessions of each exercise | a variation if a lift stalls after its deload |
| Activity | 7-day average steps, cardio minutes in the last 7 days | more steps below 8,000 a day; the morning walks when under 150 min a week |

The dashboard refreshes them when you open it. For a nightly refresh (e.g. cron):
`uv run python manage.py coach_run_rules`.

- **Workouts:** Training → your routine → start the day (gym mode) and log weight, reps and RIR for each set.
- **Meals:** Nutrition → Aesthetic 165 - cut → log to a meal. Protein and calorie totals are shown against the goals.
- **Body:** Coach → **Weekly check-in**. Log your weight (daily is best; the 7-day average is what's
  charted), waist, shoulders, chest, arms and thighs once a week, and optionally a progress photo.
  The page charts your weight against the plan, your waist, and your **shoulder-to-waist ratio**
  (the V-taper, calculated for you; 1.6 is the classic target). Everything is also visible in wger's
  own Measurements and Gallery pages.
- **Cardio & steps:** Coach → **Cardio & steps**. Log the day's steps and each walk (type, morning
  or after lifting, minutes, incline %, speed). The page charts your daily steps against the goal
  and lists the last 14 days. Steps go into wger's Steps measurement, so health-app imports land
  in the same place.
- **Goal:** Coach → **Goal** holds your target weight and date, weekly pace, protein, steps and
  focus areas. The seed command fills it in for you; new users set it there.

## 4. How the weights go up

Every exercise uses **double progression** (`wger/coach/progression.py`). After each session:

| You logged | Next session |
|---|---|
| Every set at the top of the range (4 × 10 on 8–10) | +5 lb (dumbbells/cables), +10 lb (machines) or +20 lb (leg press), back to 8 reps |
| Every set hit the current target | Same weight, one more rep (8–10 → 9–10 → 10) |
| Fewer reps than the target | Same targets again |
| No more total reps at the same weight 3 sessions in a row | Deload: −10% weight for one session |

The first time you do an exercise there's no weight target. Log what you lifted, and the next
session builds from there. If you lift heavier than prescribed, the app follows you. You can see
upcoming targets under Training → your routine → **Table**.

To change an exercise's increment, edit `increment_lb` in `wger/coach/programs/aesthetic165.py`
and re-run the seed command with `--replace`.

## 5. Tests

```bash
DJANGO_SETTINGS_MODULE=settings.ci uv run python manage.py test wger.coach
```
