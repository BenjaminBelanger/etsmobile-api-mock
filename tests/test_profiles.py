import pytest

from lib import profiles


@pytest.fixture(autouse=True)
def restore_profiles():
    yield
    profiles.reload_profiles()


def test_the_seed_profiles_are_all_valid():
    assert profiles.get_valid_profiles() == {
        "normal",
        "semester-off",
        "internship-only",
        "internship-courses",
        "generated-light",
        "generated-busy",
        "generated-evening",
        "new-student",
    }


def test_reloading_replaces_the_profile_table():
    profiles._PROFILES.clear()
    profiles.VALID_PROFILES.clear()

    reloaded = profiles.reload_profiles()

    assert "normal" in reloaded
    assert profiles.get_valid_profiles() == set(reloaded)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("$ACTIVE_SESSION", "H2026"),
        ("session $ACTIVE_SESSION!", "session H2026!"),
        ("rien", "rien"),
        (3, 3),
        (None, None),
        (True, True),
    ],
)
def test_the_active_session_placeholder_is_expanded(value, expected):
    assert profiles._interpolate(value, "H2026") == expected


def test_the_placeholder_is_expanded_deep_inside_structures():
    value = {"a": ["$ACTIVE_SESSION", {"b": "$ACTIVE_SESSION"}]}
    assert profiles._interpolate(value, "H2026") == {"a": ["H2026", {"b": "H2026"}]}


def test_an_unknown_profile_leaves_the_courses_alone():
    courses = [{"session": "H2026", "sigle": "LOG430"}]
    assert profiles.seed_courses("inconnu", "H2026", courses) is courses


def test_a_profile_can_strip_every_course():
    profiles._PROFILES["test"] = {"global": {"stripCourses": True}}
    courses = [{"session": "H2026"}, {"session": "H2025"}]

    assert profiles.seed_courses("test", "H2026", courses) == []


def test_a_profile_can_strip_only_the_active_session():
    profiles._PROFILES["test"] = {"activeSession": {"stripCourses": True}}
    courses = [{"session": "H2026"}, {"session": "H2025"}]

    assert profiles.seed_courses("test", "H2026", courses) == [{"session": "H2025"}]


def test_a_profile_can_add_courses_to_the_active_session():
    profiles._PROFILES["test"] = {
        "activeSession": {
            "stripCourses": True,
            "addCourses": [{"sigle": "STA206", "session": "$ACTIVE_SESSION"}],
        }
    }

    result = profiles.seed_courses("test", "H2026", [{"session": "H2026"}])

    assert result == [{"sigle": "STA206", "session": "H2026"}]


def test_the_internship_profile_swaps_courses_for_a_placement():
    result = profiles.seed_courses(
        "internship-only", "H2026", [{"session": "H2026", "sigle": "LOG430"}]
    )
    assert [c["sigle"] for c in result] == ["STA206"]
    assert result[0]["session"] == "H2026"
    assert result[0]["schedule"] is None


def test_an_unknown_profile_leaves_the_programs_alone():
    programs = [{"code": "7084"}]
    assert profiles.seed_programs("inconnu", "H2026", programs) is programs


def test_a_profile_can_replace_the_program_list():
    profiles._PROFILES["test"] = {
        "global": {"replacePrograms": [{"code": "0726", "sessionDebut": "$ACTIVE_SESSION"}]}
    }

    result = profiles.seed_programs("test", "H2026", [{"code": "7084"}])

    assert result == [{"code": "0726", "sessionDebut": "H2026"}]


def test_a_profile_can_add_a_program():
    result = profiles.seed_programs("internship-only", "H2026", [{"code": "7084"}])
    assert [p["code"] for p in result] == ["7084", "0726"]
    assert result[1]["sessionDebut"] == "H2026"


def test_a_profile_without_generation_and_no_flags_has_no_config(monkeypatch):
    for name in ("COURSE_COUNT", "SCHEDULE_DAYS", "TIME_PREFERENCE"):
        monkeypatch.delenv(name, raising=False)
    assert profiles.get_generation_config("semester-off") is None


def test_a_generating_profile_exposes_its_block(monkeypatch):
    for name in ("COURSE_COUNT", "SCHEDULE_DAYS", "TIME_PREFERENCE"):
        monkeypatch.delenv(name, raising=False)

    config = profiles.get_generation_config("normal")

    assert config["count"] == 4
    assert config["allowedDays"] == ["1", "2", "3", "4", "5"]
    assert config["timePreference"] == "morning,afternoon"
    assert config["custom"] is False


def test_flags_alone_turn_generation_on(monkeypatch):
    monkeypatch.setenv("COURSE_COUNT", "2")
    monkeypatch.delenv("SCHEDULE_DAYS", raising=False)
    monkeypatch.delenv("TIME_PREFERENCE", raising=False)

    config = profiles.get_generation_config("semester-off")

    assert config == {
        "count": 2,
        "allowedDays": None,
        "timePreference": None,
        "custom": True,
    }


@pytest.mark.parametrize("raw,expected", [("0", 1), ("1", 1), ("5", 5), ("9", 5)])
def test_the_course_count_is_clamped(monkeypatch, raw, expected):
    monkeypatch.setenv("COURSE_COUNT", raw)
    assert profiles.get_generation_config("normal")["count"] == expected


def test_the_day_list_is_split_on_commas(monkeypatch):
    monkeypatch.setenv("SCHEDULE_DAYS", " 1 , 3 ,5, ")
    assert profiles.get_generation_config("normal")["allowedDays"] == ["1", "3", "5"]


def test_an_empty_day_list_means_every_day(monkeypatch):
    monkeypatch.setenv("SCHEDULE_DAYS", "")
    assert profiles.get_generation_config("normal")["allowedDays"] == []


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("morning", "morning"),
        ("morning,evening", "morning,evening"),
        ("morning,lunch", "morning"),
        ("lunch", None),
        ("", None),
    ],
)
def test_only_known_time_ranges_survive(monkeypatch, raw, expected):
    monkeypatch.setenv("TIME_PREFERENCE", raw)
    assert profiles.get_generation_config("normal")["timePreference"] == expected


def test_flags_override_the_profile_block(monkeypatch):
    monkeypatch.setenv("COURSE_COUNT", "2")
    monkeypatch.setenv("SCHEDULE_DAYS", "1")

    config = profiles.get_generation_config("normal")

    assert config["count"] == 2
    assert config["allowedDays"] == ["1"]
    assert config["timePreference"] == "morning,afternoon"
    assert config["custom"] is True
