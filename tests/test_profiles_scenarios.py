"""Tests for PROFILE and SCENARIO env-driven data variations."""

import os
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from lib import data_store, failures
from main import app


@contextmanager
def env_client(**env):
    """Yield a TestClient with the given env vars applied and the data store reloaded."""
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update({k: str(v) for k, v in env.items()})
    failures.reset_config()
    data_store.reload()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        data_store.reload()


def _active_course_sigles(client):
    active = data_store.ACTIVE_SESSION
    body = client.get("/api/Etudiant/listeCours").json()
    return [c["sigle"] for c in body["liste"] if c["session"] == active]


# --- Profiles -----------------------------------------------------------------


def test_semester_off_strips_active_courses(client):
    with env_client(PROFILE="semester-off") as c:
        assert _active_course_sigles(c) == []
        # Past sessions still carry seed courses
        assert c.get("/api/Etudiant/listeCours").json()["liste"]


def test_new_student_has_no_courses(client):
    with env_client(PROFILE="new-student") as c:
        assert c.get("/api/Etudiant/listeCours").json()["liste"] == []
        programs = c.get("/api/Etudiant/listeProgrammes").json()["liste"]
        assert any(p["code"] == "7084" for p in programs)


def test_internship_only_adds_stage_course(client):
    with env_client(PROFILE="internship-only") as c:
        assert _active_course_sigles(c) == ["STA206"]
        programs = c.get("/api/Etudiant/listeProgrammes").json()["liste"]
        assert any(p["code"] == "0725" for p in programs)


@pytest.mark.parametrize("profile,count", [("generated-light", 2), ("generated-busy", 5)])
def test_generation_count(client, profile, count):
    with env_client(PROFILE=profile) as c:
        assert len(_active_course_sigles(c)) == count


# --- Scenarios ----------------------------------------------------------------


def test_monday_holiday_adds_replaced_day(client):
    with env_client(SCENARIO="monday-holiday") as c:
        active = data_store.ACTIVE_SESSION
        days = c.get(
            "/api/Etudiant/lireJoursRemplaces", params={"session": active}
        ).json()["listeJours"]
        assert any(d.get("description") == "Jour férié" for d in days)
        for entry in days:
            if entry.get("description") == "Jour férié":
                assert entry["dateOrigine"] and entry["dateRemplacement"]


def test_semaine_relache_removes_activities(client):
    active = data_store.ACTIVE_SESSION

    def seance_count(c):
        return len(
            c.get(
                "/api/Etudiant/lireHoraireDesSeances", params={"session": active}
            ).json()["ListeDesSeances"]
        )

    baseline = seance_count(client)
    with env_client(SCENARIO="semaine-relache") as c:
        assert seance_count(c) <= baseline
