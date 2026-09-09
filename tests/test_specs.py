import pytest

from lib import resource_specs, schedule_activities

TEACHER = {"nom": "Last1", "prenom": "First1", "courriel": "first1@etsmtl.ca"}
OTHER = {"nom": "Last2", "prenom": "First2", "courriel": "first2@etsmtl.ca"}


def test_a_course_key_joins_the_sigle_and_the_group():
    assert schedule_activities.build_course_key("LOG430", "02") == "LOG430-02"


def test_an_empty_session_holds_the_three_lists():
    assert schedule_activities.empty_schedule_activities() == {
        "listeActivites": [],
        "listeEnseignants": [],
        "enseignantsParCours": {},
    }


def test_teachers_are_flattened_without_duplicates():
    flattened = schedule_activities.flatten_teachers_by_course(
        {"LOG430-02": [TEACHER, OTHER], "LOG410-01": [dict(TEACHER)]}
    )
    assert flattened == [TEACHER, OTHER]


def test_flattening_an_empty_map_gives_an_empty_list():
    assert schedule_activities.flatten_teachers_by_course({}) == []


def test_registering_a_course_updates_both_views():
    session_data = schedule_activities.empty_schedule_activities()

    schedule_activities.register_course_teachers(session_data, "LOG430", "02", [TEACHER])
    schedule_activities.register_course_teachers(session_data, "LOG410", "01", [OTHER])

    assert set(session_data["enseignantsParCours"]) == {"LOG430-02", "LOG410-01"}
    assert session_data["listeEnseignants"] == [TEACHER, OTHER]


def test_registering_the_same_course_twice_replaces_its_teachers():
    session_data = schedule_activities.empty_schedule_activities()

    schedule_activities.register_course_teachers(session_data, "LOG430", "02", [TEACHER])
    schedule_activities.register_course_teachers(session_data, "LOG430", "02", [OTHER])

    assert session_data["enseignantsParCours"]["LOG430-02"] == [OTHER]
    assert session_data["listeEnseignants"] == [OTHER]


def test_every_fixture_is_reachable_by_filename():
    assert set(resource_specs.FIXTURE_SPECS) == {
        spec.filename for spec in resource_specs.ALL_FIXTURES
    }


def test_the_session_keyed_and_generated_sets_match_the_specs():
    assert resource_specs.SESSION_KEYED_FILENAMES == {
        spec.filename for spec in resource_specs.ALL_FIXTURES if spec.session_keyed
    }
    assert resource_specs.GENERATED_FILENAMES == {
        spec.filename for spec in resource_specs.ALL_FIXTURES if spec.generated
    }


def test_replaced_days_are_seeded_rather_than_generated():
    assert resource_specs.REPLACED_DAYS.filename not in resource_specs.GENERATED_FILENAMES


@pytest.mark.parametrize(
    "spec,key,expected",
    [
        (resource_specs.EVALUATIONS, "LOG430-02", "LOG430"),
        (resource_specs.TEAMMATES, "LOG430-02", "LOG430"),
        (resource_specs.COURSES, "LOG430-02", ""),
    ],
)
def test_a_sigle_can_be_read_back_from_a_key(spec, key, expected):
    assert resource_specs.sigle_from_key(spec, key) == expected


@pytest.mark.parametrize(
    "spec,item,expected",
    [
        (resource_specs.COURSES, {"sigle": "LOG430"}, "LOG430"),
        (resource_specs.COURSE_ACTIVITIES, {"coursGroupe": "LOG430-02"}, "LOG430"),
        (resource_specs.COURSE_REVIEWS, {"Sigle": "LOG430"}, "LOG430"),
        (resource_specs.REPLACED_DAYS, {"dateOrigine": "2026-02-23"}, ""),
        (resource_specs.COURSES, {}, ""),
    ],
)
def test_a_sigle_can_be_read_back_from_an_item(spec, item, expected):
    assert resource_specs.sigle_from_item(spec, item) == expected


def test_every_list_response_points_at_a_known_fixture():
    responses = [
        value
        for name, value in vars(resource_specs).items()
        if isinstance(value, resource_specs.ListResponseSpec)
    ]
    assert responses
    for response in responses:
        assert response.fixture in resource_specs.ALL_FIXTURES
        assert response.json_list_key
        assert response.xml_root and response.xml_list and response.xml_item
