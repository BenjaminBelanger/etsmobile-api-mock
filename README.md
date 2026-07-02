# ETSMobileAPI - Local Mock Server

Local mock server that replicates the ETSMobileAPI for testing the ÉTSMobile Flutter app.

## Table of Contents

- [Quick Start](#quick-start)
- [Schedule Editor UI](#schedule-editor-ui)
- [Supported Format](#supported-format)
- [Endpoints](#endpoints)
- [Managing Courses](#managing-courses)
- [Profiles](#profiles)
- [Scenarios](#scenarios)
- [Failure Injection](#failure-injection)
- [Sample Data](#sample-data)
- [Authentication](#authentication)
- [Customizing Data](#customizing-data)
- [Connecting the Flutter App](#connecting-the-flutter-app)

## Quick Start

```bash
pip install -r requirements.txt
python start.py
```

This launches an interactive menu to pick a student profile, an optional calendar scenario, and starts the server. The server runs at `http://localhost:8080`. You can access API docs at `http://localhost:8080/docs`.

## Schedule Editor UI

A visual weekly-schedule editor is served at **`http://localhost:8080/editor`**
(the root `/` redirects there). It renders the active session's courses in a
Monday–Saturday week grid and lets you reshape the schedule directly — every
change is written back to the mock and immediately reflected by the API
endpoints (`listeCours`, `listeHoraireEtProf`, `lireHoraireDesSeances`, …), so
the Flutter app sees the edited schedule.

What you can do:

| Action | How |
|--------|-----|
| **Move** a course/lab | Drag the block to another day or time (duration is preserved) |
| **Resize** | Drag the top or bottom handle to change start/end (snaps to 15 min) |
| **Delete** | Click the `×` on a block, or select and press `Delete` — it goes to the trash |
| **Restore** | Click *Restaurer* next to a course in the trash panel |
| **Add** | *Ajouter un cours* — pick a sigle (autocompletes from the catalog), day, time, and type |
| **Undo / Redo** | Toolbar buttons or `Ctrl+Z` / `Ctrl+Y` |
| **Reset** | *Réinitialiser* reverts a session to its original generated schedule |
| **Switch session** | Session dropdown in the header |

### How edits are stored

Edits are persisted per session to `seed/schedule_overrides.json`
(git-ignored). When an override exists for a session, its courses replace the
generated/seed courses for that session everywhere in the API. Undo/redo
history lives in memory and resets when the server restarts; *Réinitialiser*
(or deleting `seed/schedule_overrides.json`) clears an override entirely.

The editor is also a plain JSON API under `/editor/api/*` — see
`http://localhost:8080/docs` for the request schemas.



The server supports both JSON (default) and XML responses:

```bash
# JSON (default)
curl http://localhost:8080/api/Etudiant/infoEtudiant

# XML
curl -H "Accept: application/xml" http://localhost:8080/api/Etudiant/infoEtudiant
```

## Endpoints

All endpoints are `GET /api/Etudiant/...`:

| Endpoint | Parameters | Description |
|----------|------------|-------------|
| `helloWorld` | - | Returns "Hello World" |
| `echo` | `chaine` | Echoes back the string |
| `infoEtudiant` | - | Student profile |
| `listeCours` | - | All courses |
| `listeCoursIntervalleSessions` | `sessionDebut`, `sessionFin` | Courses in session range |
| `listeProgrammes` | - | Student programs |
| `listeSessions` | - | All sessions |
| `lireEvaluationCours` | `session` | Course evaluations for a session |
| `lireHoraireDesSeances` | `session`, `coursGroupe`?, `dateDebut`?, `dateFin`? | Course activity sessions |
| `listeHoraireEtProf` | `session` | Schedule activities + professors |
| `listeElementsEvaluation` | `session`, `sigle`, `groupe` | Grades and class statistics |
| `lireHoraire` | `session`, `prefixe` | Courses by prefix with professors |
| `listeHoraireExamensFin` | `session` | Final exam schedules |
| `lireJoursRemplaces` | `session` | Replaced days |
| `listeCoequipiers` | `session`, `sigle`, `groupe`, `nomElementEval` | Teammates |

## Managing Courses

Courses are defined in `seed/courses.json`. Data is computed at startup.

```bash
# Interactive CLI to add/remove courses
python manage_seed.py
```

You can also use the programmatic API:

```python
from manage_seed import add_course_to_seed, remove_course_from_seed

add_course_to_seed(
    session="H2026",
    sigle="LOG999",
    titre="My New Course",
    schedule={"jour": "2", "journee": "Mardi", "heureDebut": "09:00", "heureFin": "12:30",
              "codeActivite": "C", "nomActivite": "Activité de cours"},
)
```

## Profiles

The easiest way to pick a profile is `python start.py`. You can also set the `PROFILE` environment variable directly:

```bash
PROFILE=semester-off uvicorn main:app --port 8080 --reload --reload-include "*.json"
```

| Profile | Description |
|---------|-------------|
| `normal` (default) | 4 generated courses + labs, Mon-Fri mornings/afternoons |
| `semester-off` | No courses in active session |
| `internship-only` | Coop program, no courses |
| `internship-courses` | Coop program + LOG410 only |
| `new-student` | Brand-new student, no sessions or courses |
| `generated-light` | 2 courses + labs, Mon-Fri mornings |
| `generated-busy` | 5 courses + labs, Mon-Fri |
| `generated-evening` | 3 courses + labs, Mon-Fri evenings |

Profiles are defined in `seed/profiles.json`. Add a new profile by adding a JSON object.

### Custom Generation

The interactive menu (`python start.py`) offers a "Custom" option that prompts for course count, schedule days, and time preference.

You can also set these values directly with environment variables, from any profile:

| Variable | Description | Example |
|----------|-------------|---------|
| `COURSE_COUNT` | Number of courses (1-5) | `COURSE_COUNT=2` |
| `SCHEDULE_DAYS` | Comma-separated day codes (1=Mon, 6=Sat) | `SCHEDULE_DAYS=1,3,5` |
| `TIME_PREFERENCE` | `morning`, `afternoon`, `evening` (comma-separated for multiple) | `TIME_PREFERENCE=morning,evening` |

```bash
COURSE_COUNT=2 SCHEDULE_DAYS=1,3,5 uvicorn main:app --port 8080 --reload --reload-include "*.json"
```

### Semester week (shift the session calendar)

By default, the mock uses the real session calendar from `seed/sessions.json`, so running the server near the end of a semester leaves few upcoming activities, exams in the past, and most grades already published. To simulate being at a specific week of the active session, set:

```bash
SEMESTER_WEEK=3 uvicorn main:app --port 8080 --reload --reload-include "*.json"
```

This shifts the active session's `dateDebut` (and all other date fields) so that today falls at the chosen week. The next session is shifted by the same offset to preserve the gap between them.

## Scenarios

Scenarios apply calendar modifications to the active session (skipped days, replaced days). Select a scenario from the `start.py` menu, or set the `SCENARIO` environment variable:

```bash
SCENARIO=semaine-relache uvicorn main:app --port 8080 --reload --reload-include "*.json"
```

| Scenario | Description |
|----------|-------------|
| `none` (default) | No calendar modifications |
| `friday-off` | Next Friday has no courses |
| `semaine-relache` | Next full week off |
| `monday-holiday` | Next Monday is a holiday (replaced by Tuesday) |
| `long-weekend` | Next Friday + Monday off |

Scenarios are defined declaratively in `seed/scenarios.json`.

## Failure Injection

The mock can simulate flaky-network and broken-server conditions. Failures are configured at startup via env vars and can be tweaked at runtime through `/admin/failures`.

### Environment variables

| Variable | Effect | Example |
|----------|--------|---------|
| `LATENCY_MS` | Add latency before every API response. Accepts a fixed int or a `min-max` range. | `LATENCY_MS=500` or `LATENCY_MS=100-800` |
| `ERROR_RATE` | Probability (0.0-1.0) that any API call returns a 500. | `ERROR_RATE=0.1` |
| `FAIL_ENDPOINTS` | Comma-separated endpoint names that always return 503. Use `*` for all endpoints. | `FAIL_ENDPOINTS=listeCoequipiers,lireEvaluationCours` |
| `TIMEOUT_ENDPOINTS` | Endpoints that hang the request. | `TIMEOUT_ENDPOINTS=lireEvaluationCours` |
| `TIMEOUT_DURATION_S` | How long timeout endpoints sleep before giving up with a 504. | `TIMEOUT_DURATION_S=30` (default 60) |
| `MALFORMED` | Truncate every successful 2xx response body in half. | `MALFORMED=true` |
| `AUTH_REQUIRED` | Return 401 on API requests that lack an `Authorization` header. | `AUTH_REQUIRED=true` |

```bash
LATENCY_MS=200-600 ERROR_RATE=0.1 uvicorn main:app --port 8080 --reload
```

### Runtime control via admin endpoint

```bash
# View current config
curl http://localhost:8080/admin/failures

# Patch any subset of fields
curl -X PATCH http://localhost:8080/admin/failures \
  -H 'Content-Type: application/json' \
  -d '{"latencyMs": "100-500", "errorRate": 0.2, "failEndpoints": ["listeCoequipiers"]}'

# Reset everything to defaults
curl -X DELETE http://localhost:8080/admin/failures
```

PATCH body fields: `latencyMs` (int or `"min-max"` string), `errorRate` (0.0-1.0), `failEndpoints` (list), `timeoutEndpoints` (list), `timeoutDurationS` (float), `malformed` (bool), `authRequired` (bool). All optional.

### Named presets via manage_failures.py

For day-to-day use you usually don't want to hand-write JSON. The `manage_failures.py` CLI applies named presets defined in `seed/failure_presets.json`:

```bash
python manage_failures.py list             # show available presets
python manage_failures.py status           # show current config
python manage_failures.py flaky            # apply a preset
python manage_failures.py reset            # clear everything (alias: off)
python manage_failures.py custom --error-rate 0.5 --latency 100-500 --fail listeCoequipiers
```

| Preset | Effect |
|--------|--------|
| `flaky` | 100-800ms latency, 30% random 500s |
| `slow` | 2-5s latency on every API call |
| `outage` | Every API endpoint returns 503 |
| `partial-outage` | Grades and teammates endpoints down |
| `auth` | Require an Authorization header |
| `corrupt` | Truncate every successful response body |
| `timeout-grades` | Grade endpoints hang for 30s before returning 504 |
| `chaos` | Latency + errors + corrupted bodies all at once |

Add new presets by editing `seed/failure_presets.json`.

## Sample Data

The mock server returns data for a fictional ÉTS software engineering student with:

- **Sessions**: H2024, É2024, A2024, H2025, É2025, A2025, H2026
- **15 seed courses** across 6 sessions with grades, evaluations, schedules, and teammates
- **Active session**: Determined by today's date (Jan-Apr = Hiver, May-Aug = Été, Sep-Dec = Automne). Courses are generated from `seed/pools.json` unless the profile specifies otherwise
- **Past sessions**: Completed courses with final grades

## Authentication

No authentication is required. The server accepts any `Authorization: Bearer <token>` header (or none at all).

## Customizing Data

- **Course data**: Edit `seed/courses.json` and restart (or let `--reload` handle it)
- **Sessions, student info, programs, replaced days**: Edit directly in `seed/`
- **Professors**: Edit `seed/professors.json`
- **Random generation pools**: Edit `seed/pools.json` (rooms, eval templates, schedule slots, course catalog)
- **Profiles**: Edit `seed/profiles.json`
- **Scenarios**: Edit `seed/scenarios.json`

## Connecting the Flutter App

The following changes in the Flutter app are needed to point it at this mock server. **Do not commit these changes!**

### 1. Start the mock server

```bash
cd etsmobile-api-mock
python start.py
```

### 2. Change the API host

In `lib/domain/constants/urls.dart`, replace the host with your local server:

```dart
// Before
static const String signetsAPI = "etsmobileapi.etsmtl.ca";

// After - use "10.0.2.2:8080" for Android emulator, "localhost:8080" for iOS emulator
static const String signetsAPI = "10.0.2.2:8080";
```

### 3. Switch from HTTPS to HTTP

The mock server runs in HTTP. In `lib/data/services/signets-api/request_builder_service.dart`, change `Uri.https` to `Uri.http`:

```dart
// Before
final uri = Uri.https(Urls.signetsAPI, endpoint, queryParameters);

// After
final uri = Uri.http(Urls.signetsAPI, endpoint, queryParameters);
```

### 4. Override the base URL

In `lib/locator.dart`, pass a local `baseUrl` to the `SignetsClient`:

```dart
// Before
locator.registerLazySingleton(() => SignetsClient(dio));

// After - match the host you used in step 2
locator.registerLazySingleton(() => SignetsClient(dio, baseUrl: 'http://10.0.2.2:8080/api/Etudiant/'));
```

### 5. Run the app

```bash
cd Notre-Dame
flutter run
```

The mock server requires no authentication, so you can skip past or stub out the login flow.

### Platform-specific hosts

| Platform | Host to use |
|----------|-------------|
| Android emulator | `10.0.2.2:8080` |
| iOS emulator | `localhost:8080` |
