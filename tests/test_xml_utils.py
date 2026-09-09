from xml.etree.ElementTree import fromstring

from lib import xml_utils

DECL = '<?xml version="1.0" encoding="utf-8"?>'


def parse(xml):
    assert xml.startswith(DECL)
    return fromstring(xml[len(DECL):])


def test_a_list_document_wraps_every_item_in_the_item_tag():
    xml = xml_utils.build_list_xml(
        "ListeCours",
        "liste",
        "Cours",
        [{"sigle": "LOG430", "groupe": "01"}, {"sigle": "LOG410", "groupe": "02"}],
    )
    root = parse(xml)

    assert root.tag == "ListeCours"
    assert [item.tag for item in root.find("liste")] == ["Cours", "Cours"]
    assert root.find("liste/Cours/sigle").text == "LOG430"


def test_every_document_carries_an_erreur_element():
    root = parse(xml_utils.build_list_xml("ListeCours", "liste", "Cours", []))
    assert root.find("erreur") is not None
    assert root.find("erreur").text is None

    root = parse(xml_utils.build_list_xml("ListeCours", "liste", "Cours", [], "boom"))
    assert root.find("erreur").text == "boom"


def test_empty_and_none_values_render_as_empty_elements():
    root = parse(xml_utils.build_flat_xml("Etudiant", {"nom": "", "prenom": None}))
    assert root.find("nom").text is None
    assert root.find("prenom").text is None


def test_booleans_render_lowercase():
    root = parse(xml_utils.build_flat_xml("Etudiant", {"masculin": True}))
    assert root.find("masculin").text == "true"


def test_numbers_render_as_text():
    root = parse(xml_utils.build_flat_xml("Etudiant", {"solde": 12}))
    assert root.find("solde").text == "12"


def test_a_flat_document_skips_list_values():
    root = parse(xml_utils.build_flat_xml("Etudiant", {"nom": "Last0", "liste": [{}]}))
    assert root.find("nom").text == "Last0"
    assert root.find("liste") is None


def test_nested_lists_use_the_mapped_item_tag():
    xml = xml_utils.build_list_xml(
        "ListeCoursHoraire",
        "listeCours",
        "CoursHoraire",
        [{"sigle": "LOG430", "listeProf": [{"nom": "Last1"}]}],
    )
    root = parse(xml)

    assert [e.tag for e in root.find("listeCours/CoursHoraire/listeProf")] == [
        "Enseignant"
    ]
    assert root.find("listeCours/CoursHoraire/listeProf/Enseignant/nom").text == "Last1"


def test_an_unmapped_nested_list_falls_back_to_item():
    xml = xml_utils.build_list_xml(
        "Root", "liste", "Item", [{"inconnu": [{"champ": "valeur"}]}]
    )
    assert parse(xml).find("liste/Item/inconnu/Item/champ").text == "valeur"


def test_a_nested_dict_becomes_a_nested_element():
    xml = xml_utils.build_list_xml(
        "Root", "liste", "Item", [{"schedule": {"jour": "1"}}]
    )
    assert parse(xml).find("liste/Item/schedule/jour").text == "1"


def test_a_dual_list_document_holds_both_lists():
    xml = xml_utils.build_dual_list_xml(
        "ListeActivitesEtProfs",
        "listeActivites",
        "HoraireActivite",
        [{"sigle": "LOG430"}],
        "listeEnseignants",
        "Enseignant",
        [{"nom": "Last1"}, {"nom": "Last2"}],
    )
    root = parse(xml)

    assert len(root.find("listeActivites")) == 1
    assert [e.find("nom").text for e in root.find("listeEnseignants")] == [
        "Last1",
        "Last2",
    ]


def test_an_evaluation_document_keeps_summary_fields_beside_the_list():
    xml = xml_utils.build_evaluation_xml(
        {"noteACeJour": "85,0", "liste": [{"nom": "TP1"}]}
    )
    root = parse(xml)

    assert root.tag == "ListeElementsEvaluation"
    assert root.find("noteACeJour").text == "85,0"
    assert [e.tag for e in root.find("liste")] == ["ElementEvaluation"]
    assert root.find("liste/ElementEvaluation/nom").text == "TP1"


def test_an_evaluation_document_without_a_list_still_has_the_wrapper():
    root = parse(xml_utils.build_evaluation_xml({"noteACeJour": ""}))
    assert root.find("liste") is not None
    assert len(root.find("liste")) == 0


def test_a_string_document_is_a_bare_string_element():
    assert xml_utils.build_string_xml("Hello World") == "<string>Hello World</string>"


def test_special_characters_are_escaped():
    xml = xml_utils.build_flat_xml("Etudiant", {"nom": "Ben & <Jerry>"})
    assert "&amp;" in xml and "&lt;Jerry&gt;" in xml
    assert parse(xml).find("nom").text == "Ben & <Jerry>"
