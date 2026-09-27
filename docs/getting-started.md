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

- **Workouts:** Training → your routine → start the day (gym mode) and log weight, reps and RIR for each set.
- **Meals:** Nutrition → Aesthetic 165 - cut → log to a meal. Protein and calorie totals are shown against the goals.
- **Body:** Body weight for daily weigh-ins, and Measurements for waist/shoulders/steps.

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
