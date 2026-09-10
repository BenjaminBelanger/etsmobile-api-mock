# ETSMobileAPI - Local Mock Server

Local mock server that replicates the ETSMobileAPI for testing the ÉTSMobile Flutter app.

## Table of Contents

- [Quick Start](#quick-start)
- [Schedule Editor UI](#schedule-editor-ui)
- [Tests](#tests)
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

To skip the menu, pass the configuration as flags instead:

```bash
python start.py --profile semester-off
python start.py --courses 2 --days 1,3,5 --time morning
python start.py --scenario semaine-relache --semester-week 3
```

`python start.py --help` lists every profile, scenario and day code.

## Schedule Editor UI

<img width="2554" height="1235" alt="Screenshot 2026-09-09 222414" src="https://github.com/user-attachments/assets/3efc80ec-41c3-4743-ace5-e77ed056a4c7" />

A visual weekly-schedule editor is served at `http://localhost:8080/editor`
(the root `/` redirects there). It shows the active session's courses in a week
grid and lets you move, resize, add and delete them. Edits are written back to
the mock, so the API endpoints serve the edited schedule.

Nothing extra is needed to run it. Start the server and open the page:

```bash
python start.py
```

### Editing scopes

The toolbar switches between two scopes:

- **All weeks** edits the weekly slot, so the change applies to every occurrence
  of that block.
- **This occurrence** edits only the displayed week.

An occurrence with a week-specific change is marked as modified and can only be
dragged in **This occurrence**; reset it to put it back on the series slot.

### Front-end build

The editor's front-end assets are already built and committed, so running the
mock only needs Python. To rebuild:

```bash
cd web
npm install
npm run build
```

## Tests

```bash
python -m pytest tests/    # server, editor backend, CLIs and the UI suite
```

The editor UI is covered by a jsdom suite that drives `web/assets/app.js`
against the real `web/index.html`. It needs the front-end dev dependencies:

```bash
cd web
npm install
npm test
```

`python -m pytest tests/` runs that suite too when `web/node_modules` is
present, and skips it otherwise.

## Supported Format

The server supports both JSON (default) and XML responses:

```bash
# JSON (default)
curl http://localhost:8080/api/Etudiant/infoEtudiant

# XML
curl -H "Accept: application/xml" http://localhost:8080/api/Etudiant/infoEtudiant
```

In Windows PowerShell 5.1, use `curl.exe`.

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

Pick a profile from the `python start.py` menu, or name it directly:

```bash
python start.py --profile semester-off
```

| Profile | Description |
|---------|-------------|
| `normal` (default) | 4 generated courses + labs, Mon-Fri mornings/afternoons |
| `semester-off` | No courses in active session |
| `internship-only` | Coop program, no courses |
| `internship-courses` | Coop program + 2 generated evening courses |
| `new-student` | Brand-new student, no sessions or courses |
| `generated-light` | 2 courses + labs, Mon-Fri mornings |
| `generated-busy` | 5 courses + labs, Mon-Fri |
| `generated-evening` | 3 courses + labs, Mon-Fri evenings |

Profiles are defined in `seed/profiles.json`. Add a new profile by adding a JSON object.

### Custom Generation

The interactive menu (`python start.py`) offers a "Custom" option that prompts for course count, schedule days, and time preference.

You can set the same values as flags, on top of any profile:

| Flag | Description |
|------|-------------|
| `--courses N` | Number of courses (1-5) |
| `--days 1,3,5` | Comma-separated day codes (1=Mon, 6=Sat) |
| `--time morning` | `morning`, `afternoon`, `evening` (comma-separated for multiple) |

```bash
python start.py --courses 2 --days 1,3,5
python start.py --profile generated-busy --time evening
```

Invalid values are rejected before the server starts.

### Semester week (shift the session calendar)

By default, the mock uses the real session calendar from `seed/sessions.json`, so running the server near the end of a semester leaves few upcoming activities, exams in the past, and most grades already published. To simulate being at a specific week of the active session, set:

```bash
python start.py --semester-week 3
```

This shifts the active session's `dateDebut` (and all other date fields) so that today falls at the chosen week. The next session is shifted by the same offset to preserve the gap between them.

## Scenarios

Scenarios apply calendar modifications to the active session (skipped days, replaced days). Select a scenario from the `start.py` menu, or name it directly:

```bash
python start.py --scenario semaine-relache
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

The mock can simulate broken-server conditions. Set them at startup with flags, or change them on a running server through `/admin/failures`.

### Startup flags

| Flag | Effect |
|------|--------|
| `--failures PRESET` | Apply a named preset ([list](#named-presets-via-manage_failurespy)) |
| `--latency MS` | Add latency before every API response. Fixed (`500`) or a range (`100-800`) |
| `--error-rate R` | Probability (0.0-1.0) that any API call returns a 500 |
| `--fail ENDPOINT` | Endpoint that always returns 503. Repeatable, `*` for all |
| `--timeout ENDPOINT` | Endpoint that hangs the request. Repeatable, `*` for all |
| `--timeout-duration S` | How long a hanging endpoint sleeps before a 504 (default 60) |
| `--malformed` | Truncate every successful 2xx response body in half |
| `--auth` | Return 401 on API requests without an `Authorization` header |

```bash
python start.py --failures flaky
python start.py --latency 200-600 --error-rate 0.1
python start.py --profile semester-off --auth
```

A preset can be adjusted by adding flags after it. `--failures flaky
--error-rate 0.9` keeps the preset's latency and replaces its error rate.
`--malformed` and `--auth` each have a `--no-` form.

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
