from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .xml_utils import (
    build_dual_list_xml,
    build_evaluation_xml,
    build_flat_xml,
    build_list_xml,
    build_string_xml,
)

_XML_CONTENT_TYPE = "application/xml; charset=utf-8"
_MISSING_PARAM_MSG = "Un des paramètres obligatoires est absent de la requête."


def wants_xml(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "application/xml" in accept or "text/xml" in accept


def require(**params) -> None:
    if any(not v for v in params.values()):
        raise HTTPException(status_code=400, detail=_MISSING_PARAM_MSG)


def respond_string(request: Request, value: str) -> Response:
    if wants_xml(request):
        return Response(content=build_string_xml(value), media_type=_XML_CONTENT_TYPE)
    return JSONResponse(value)


def respond_flat(
    request: Request, xml_root: str, data: dict, error: str = ""
) -> Response:
    if wants_xml(request):
        return Response(
            content=build_flat_xml(xml_root, data, error), media_type=_XML_CONTENT_TYPE
        )
    return JSONResponse({**data, "erreur": error})


def respond_list(
    request: Request,
    items: list,
    json_list_key: str,
    xml_root: str,
    xml_list: str,
    xml_item: str,
    error: str = "",
) -> Response:
    if wants_xml(request):
        xml = build_list_xml(xml_root, xml_list, xml_item, items, error)
        return Response(content=xml, media_type=_XML_CONTENT_TYPE)
    return JSONResponse({json_list_key: items, "erreur": error})


def respond_dual_list(
    request: Request,
    xml_root: str,
    list1_key: str,
    item1_tag: str,
    items1: list,
    list2_key: str,
    item2_tag: str,
    items2: list,
) -> Response:
    if wants_xml(request):
        xml = build_dual_list_xml(
            xml_root,
            list1_key,
            item1_tag,
            items1,
            list2_key,
            item2_tag,
            items2,
        )
        return Response(content=xml, media_type=_XML_CONTENT_TYPE)
    return JSONResponse({list1_key: items1, list2_key: items2, "erreur": ""})


def respond_evaluation(request: Request, eval_data: dict) -> Response:
    if wants_xml(request):
        xml = build_evaluation_xml(eval_data)
        return Response(content=xml, media_type=_XML_CONTENT_TYPE)
    return JSONResponse({**eval_data, "erreur": ""})
