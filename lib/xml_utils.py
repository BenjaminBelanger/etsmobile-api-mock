"""XML builder to produce Signets-format XML from Python dicts/lists."""

from xml.etree.ElementTree import Element, SubElement, tostring

_XML_DECL = '<?xml version="1.0" encoding="utf-8"?>'


def _set_element_text(element: Element, value):
    if value is None or value == "":
        return
    if isinstance(value, bool):
        element.text = str(value).lower()
    else:
        element.text = str(value)


def _add_scalar_fields(parent: Element, data: dict):
    for key, value in data.items():
        if isinstance(value, list):
            continue
        _set_element_text(SubElement(parent, key), value)


def _add_list_items(parent: Element, items: list[dict], item_tag: str):
    for item in items:
        item_el = SubElement(parent, item_tag)
        for key, value in item.items():
            if isinstance(value, list):
                nested_list = SubElement(item_el, key)
                for nested_item in value:
                    if isinstance(nested_item, dict):
                        nested_tag = _resolve_item_tag(key)
                        nested_el = SubElement(nested_list, nested_tag)
                        _add_scalar_fields(nested_el, nested_item)
            elif isinstance(value, dict):
                nested_el = SubElement(item_el, key)
                _add_scalar_fields(nested_el, value)
            else:
                _set_element_text(SubElement(item_el, key), value)


def _resolve_item_tag(list_key: str) -> str:
    mapping = {
        "listeProf": "Enseignant",
        "listeEnseignants": "Enseignant",
        "listeActivites": "HoraireActivite",
        "liste": "ElementEvaluation",
        "listeEvaluations": "EvaluationCours",
        "listeCours": "CoursHoraire",
        "listeHoraire": "HoraireExamenFinal",
        "listeJours": "JourRemplace",
        "listeCoequipiers": "Personne",
    }
    return mapping.get(list_key, "Item")


def _make_root(tag: str, error: str = "") -> Element:
    root = Element(tag)
    err = SubElement(root, "erreur")
    if error:
        err.text = error
    return root


def build_list_xml(
    root_tag: str,
    list_tag: str,
    item_tag: str,
    items: list[dict],
    error: str = "",
) -> str:
    root = _make_root(root_tag, error)
    wrapper = SubElement(root, list_tag)
    _add_list_items(wrapper, items, item_tag)
    return _XML_DECL + tostring(root, encoding="unicode")


def build_flat_xml(root_tag: str, data: dict, error: str = "") -> str:
    root = _make_root(root_tag, error)
    _add_scalar_fields(root, data)
    return _XML_DECL + tostring(root, encoding="unicode")


def build_dual_list_xml(
    root_tag: str,
    list1_tag: str,
    item1_tag: str,
    items1: list[dict],
    list2_tag: str,
    item2_tag: str,
    items2: list[dict],
    error: str = "",
) -> str:
    root = _make_root(root_tag, error)
    wrapper1 = SubElement(root, list1_tag)
    _add_list_items(wrapper1, items1, item1_tag)

    wrapper2 = SubElement(root, list2_tag)
    _add_list_items(wrapper2, items2, item2_tag)

    return _XML_DECL + tostring(root, encoding="unicode")


def build_evaluation_xml(data: dict, error: str = "") -> str:
    root = _make_root("ListeElementsEvaluation", error)
    for key, value in data.items():
        if key == "liste":
            continue
        _set_element_text(SubElement(root, key), value)

    wrapper = SubElement(root, "liste")
    _add_list_items(wrapper, data.get("liste", []), "ElementEvaluation")

    return _XML_DECL + tostring(root, encoding="unicode")


def build_string_xml(value: str) -> str:
    root = Element("string")
    root.text = value
    return tostring(root, encoding="unicode")
