"""API routes under /api/Etudiant/..."""

from fastapi import APIRouter, Query, Request

from .data_store import empty_evaluation, load, load_session
from .responses import (
    require,
    respond_dual_list,
    respond_evaluation,
    respond_flat,
    respond_list,
    respond_string,
)
from .resource_specs import (
    COURSE_ACTIVITIES,
    COURSE_ACTIVITY_LIST_RESPONSE,
    COURSE_LIST_RESPONSE,
    COURSE_REVIEW_LIST_RESPONSE,
    COURSE_SCHEDULE,
    COURSE_SCHEDULE_LIST_RESPONSE,
    COURSES,
    EVALUATIONS,
    FINAL_EXAM_LIST_RESPONSE,
    ListResponseSpec,
    PROGRAM_LIST_RESPONSE,
    REPLACED_DAY_LIST_RESPONSE,
    SCHEDULE_ACTIVITIES,
    SESSION_LIST_RESPONSE,
    STUDENT_INFO,
    TEAMMATE_LIST_RESPONSE,
    TEAMMATES,
)
from .schedule_activities import (
    build_course_key,
    empty_schedule_activities,
    flatten_teachers_by_course,
)
from .sessions import session_rank

router = APIRouter(prefix="/api/Etudiant")


def _respond_list_resource(request: Request, spec: ListResponseSpec, items) -> object:
    return respond_list(
        request,
        items,
        json_list_key=spec.json_list_key,
        xml_root=spec.xml_root,
        xml_list=spec.xml_list,
        xml_item=spec.xml_item,
    )


def _load_list_resource(request: Request, spec: ListResponseSpec):
    return _respond_list_resource(request, spec, load(spec.fixture.filename))


def _load_session_list_resource(request: Request, spec: ListResponseSpec, session: str):
    require(session=session)
    return _respond_list_resource(
        request,
        spec,
        load_session(spec.fixture.filename, session, spec.session_default),
    )


@router.get("/helloWorld")
def hello_world(request: Request):
    return respond_string(request, "Hello World")


@router.get("/echo")
def echo(request: Request, chaine: str = Query(None)):
    require(chaine=chaine)
    return respond_string(request, chaine)


@router.get("/infoEtudiant")
def info_etudiant(request: Request):
    return respond_flat(request, "Etudiant", load(STUDENT_INFO.filename))


@router.get("/listeCours")
def liste_cours(request: Request):
    return _load_list_resource(request, COURSE_LIST_RESPONSE)


@router.get("/listeCoursIntervalleSessions")
def liste_cours_intervalle(
    request: Request,
    sessionDebut: str = Query(None),
    sessionFin: str = Query(None),
):
    require(sessionDebut=sessionDebut, sessionFin=sessionFin)
    courses = load(COURSES.filename)
    start = session_rank(sessionDebut)
    end = session_rank(sessionFin)
    filtered = [c for c in courses if start <= session_rank(c["session"]) <= end]
    return _respond_list_resource(request, COURSE_LIST_RESPONSE, filtered)


@router.get("/listeProgrammes")
def liste_programmes(request: Request):
    return _load_list_resource(request, PROGRAM_LIST_RESPONSE)


@router.get("/listeSessions")
def liste_sessions(request: Request):
    return _load_list_resource(request, SESSION_LIST_RESPONSE)


@router.get("/lireEvaluationCours")
def lire_evaluation_cours(request: Request, session: str = Query(None)):
    return _load_session_list_resource(request, COURSE_REVIEW_LIST_RESPONSE, session)


@router.get("/lireHoraireDesSeances")
def lire_horaire_des_seances(
    request: Request,
    session: str = Query(None),
    coursGroupe: str = Query(None),
    dateDebut: str = Query(None),
    dateFin: str = Query(None),
):
    require(session=session)
    items = load_session(COURSE_ACTIVITIES.filename, session)

    if coursGroupe:
        items = [item for item in items if item.get("coursGroupe") == coursGroupe]
    if dateDebut:
        items = [item for item in items if item.get("dateDebut", "") >= dateDebut]
    if dateFin:
        end_cutoff = dateFin + "T23:59:59"
        items = [item for item in items if item.get("dateFin", "") <= end_cutoff]

    return _respond_list_resource(request, COURSE_ACTIVITY_LIST_RESPONSE, items)


@router.get("/listeHoraireEtProf")
def liste_horaire_et_prof(request: Request, session: str = Query(None)):
    require(session=session)
    session_data = load_session(
        SCHEDULE_ACTIVITIES.filename,
        session,
        empty_schedule_activities(),
    )
    activities = session_data.get("listeActivites", [])
    teachers = session_data.get("listeEnseignants") or flatten_teachers_by_course(
        session_data.get("enseignantsParCours", {})
    )
    return respond_dual_list(
        request,
        xml_root="ListeActivitesEtProfs",
        list1_key="listeActivites",
        item1_tag="HoraireActivite",
        items1=activities,
        list2_key="listeEnseignants",
        item2_tag="Enseignant",
        items2=teachers,
    )


@router.get("/listeElementsEvaluation")
def liste_elements_evaluation(
    request: Request,
    session: str = Query(None),
    sigle: str = Query(None),
    groupe: str = Query(None),
):
    require(session=session, sigle=sigle, groupe=groupe)
    session_data = load_session(EVALUATIONS.filename, session, {})
    eval_data = session_data.get(build_course_key(sigle, groupe), empty_evaluation())
    return respond_evaluation(request, eval_data)


@router.get("/lireHoraire")
def lire_horaire(
    request: Request,
    session: str = Query(None),
    prefixe: str = Query(None),
):
    require(session=session, prefixe=prefixe)
    items = [
        item
        for item in load_session(COURSE_SCHEDULE.filename, session)
        if item.get("sigle", "").startswith(prefixe)
    ]
    return _respond_list_resource(request, COURSE_SCHEDULE_LIST_RESPONSE, items)


@router.get("/listeHoraireExamensFin")
def liste_horaire_examens_fin(request: Request, session: str = Query(None)):
    return _load_session_list_resource(request, FINAL_EXAM_LIST_RESPONSE, session)


@router.get("/lireJoursRemplaces")
def lire_jours_remplaces(request: Request, session: str = Query(None)):
    return _load_session_list_resource(request, REPLACED_DAY_LIST_RESPONSE, session)


@router.get("/listeCoequipiers")
def liste_coequipiers(
    request: Request,
    session: str = Query(None),
    sigle: str = Query(None),
    groupe: str = Query(None),
    nomElementEval: str = Query(None),
):
    require(session=session, sigle=sigle, groupe=groupe, nomElementEval=nomElementEval)
    course_data = load_session(TEAMMATES.filename, session, {}).get(
        build_course_key(sigle, groupe), {}
    )
    items = course_data.get(nomElementEval, [])
    return _respond_list_resource(request, TEAMMATE_LIST_RESPONSE, items)
