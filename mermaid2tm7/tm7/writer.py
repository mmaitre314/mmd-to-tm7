"""TM7 XML emission.

Emits the Microsoft Threat Modeling Tool ``.tm7`` structure (a
``DataContractSerializer`` document). The geometry-bearing parts — element
``Left``/``Top``/``Width``/``Height`` and connector ``Source*``/``Target*``/``Handle*``
— are what this project changes; the surrounding envelope follows TMT's format.

VERIFICATION GAP (honest disclosure): ``docs/04-tm7-mapping-spec.md`` §Output
verification requires every generated file to pass ``tools/tm7_validate.exe``,
which uses TMT's own serializer types and only runs on Windows/.NET. That tool and
a Windows host are **not available in this environment**, so the exact ``i:type``
discriminators and property schema below are modelled on the documented TM7 format
but have not been round-tripped through TMT here. Treat this writer as needing a
validate-on-Windows pass before production use, and reconcile with the existing
``tm7_cli.py`` generator's writer when integrating. See ``docs/investigation.md``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

_NS_MODEL = "http://schemas.datacontract.org/2004/07/ThreatModeling.Model"
_NS_ABS = "http://schemas.datacontract.org/2004/07/ThreatModeling.Model.Abstracts"
_NS_I = "http://www.w3.org/2001/XMLSchema-instance"
_NS_ARR = "http://schemas.microsoft.com/2003/10/Serialization/Arrays"


@dataclass
class Tm7Element:
    guid: str
    generic_type_id: str
    type_id: str
    name: str
    left: int
    top: int
    width: int
    height: int
    is_boundary: bool = False
    properties: dict[str, str] | None = None


@dataclass
class Tm7Flow:
    guid: str
    name: str
    source_guid: str
    target_guid: str
    source_x: int
    source_y: int
    target_x: int
    target_y: int
    handle_x: int
    handle_y: int
    properties: dict[str, str] | None = None


def _sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = text
    return el


def _abs(tag: str) -> str:
    return f"{{{_NS_ABS}}}{tag}"


def _nil(parent: ET.Element, tag: str) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.set(f"{{{_NS_I}}}nil", "true")
    return el


def _properties(parent: ET.Element, props: dict[str, str] | None) -> None:
    container = ET.SubElement(parent, _abs("Properties"))
    if not props:
        return
    for key, value in props.items():
        item = ET.SubElement(container, f"{{{_NS_ABS}}}anyType")
        kv = ET.SubElement(item, f"{{{_NS_ARR}}}KeyValueOfstringstring")
        _sub(kv, f"{{{_NS_ARR}}}Key", key)
        _sub(kv, f"{{{_NS_ARR}}}Value", value)


def _border_entry(borders: ET.Element, el: Tm7Element) -> None:
    entry = ET.SubElement(borders, _abs("KeyValueOfguidanyType"))
    _sub(entry, f"{{{_NS_ABS}}}Key", el.guid)
    value = ET.SubElement(entry, f"{{{_NS_ABS}}}Value")
    value.set(f"{{{_NS_I}}}type", "BorderBoundary" if el.is_boundary else "Border")
    _sub(value, _abs("GenericTypeId"), el.generic_type_id)
    _sub(value, _abs("Guid"), el.guid)
    _properties(value, {"Name": el.name, **(el.properties or {})})
    _sub(value, _abs("TypeId"), el.type_id)
    # geometry (namespace-default ThreatModeling.Model)
    _sub(value, "Height", str(el.height))
    _sub(value, "Left", str(el.left))
    _nil(value, "StrokeDashArray")
    _sub(value, "StrokeThickness", "1" if el.is_boundary else "0")
    _sub(value, "Top", str(el.top))
    _sub(value, "Width", str(el.width))


def _line_entry(lines: ET.Element, flow: Tm7Flow) -> None:
    entry = ET.SubElement(lines, _abs("KeyValueOfguidanyType"))
    _sub(entry, f"{{{_NS_ABS}}}Key", flow.guid)
    value = ET.SubElement(entry, f"{{{_NS_ABS}}}Value")
    value.set(f"{{{_NS_I}}}type", "Connector")
    _sub(value, _abs("GenericTypeId"), "GE.DF")
    _sub(value, _abs("Guid"), flow.guid)
    _properties(value, {"Name": flow.name, **(flow.properties or {})})
    _sub(value, _abs("TypeId"), "GE.DF")
    _sub(value, "HandleX", str(flow.handle_x))
    _sub(value, "HandleY", str(flow.handle_y))
    _nil(value, "PortSource")
    _nil(value, "PortTarget")
    _sub(value, "SourceGuid", flow.source_guid)
    _sub(value, "SourceX", str(flow.source_x))
    _sub(value, "SourceY", str(flow.source_y))
    _sub(value, "TargetGuid", flow.target_guid)
    _sub(value, "TargetX", str(flow.target_x))
    _sub(value, "TargetY", str(flow.target_y))


def build_tm7(
    title: str,
    model_guid: str,
    elements: list[Tm7Element],
    flows: list[Tm7Flow],
    *,
    version: str = "4.1.0.4",
) -> ET.ElementTree:
    """Build a TM7 ElementTree.

    ``elements`` must already be ordered outermost boundary first (z-order), per
    ``docs/04-tm7-mapping-spec.md`` §Boundary mapping.
    """
    ET.register_namespace("", _NS_MODEL)
    ET.register_namespace("i", _NS_I)
    ET.register_namespace("a", _NS_ABS)
    ET.register_namespace("b", _NS_ARR)

    root = ET.Element(f"{{{_NS_MODEL}}}ThreatModel")

    surfaces = _sub(root, "DrawingSurfaceList")
    surface = ET.SubElement(surfaces, "DrawingSurfaceModel")
    _sub(surface, _abs("GenericTypeId"), "DFD")
    _sub(surface, _abs("Guid"), model_guid)
    _properties(surface, None)
    _sub(surface, _abs("TypeId"), "DrawingSurface")

    borders = _sub(surface, "Borders")
    for el in elements:
        _border_entry(borders, el)

    _sub(surface, "Header", title)

    lines = _sub(surface, "Lines")
    for flow in flows:
        _line_entry(lines, flow)

    _sub(surface, "Zoom", "1")

    _sub(root, "MetaInformation")
    _sub(root, "Notes")
    _sub(root, "ThreatInstances")
    _sub(root, "ThreatGenerationEnabled", "true")
    _sub(root, "Validations")
    _sub(root, "Version", version)
    _sub(root, "Views")
    _sub(root, "Contributors")

    return ET.ElementTree(root)


def to_string(tree: ET.ElementTree) -> str:
    ET.indent(tree, space="  ")
    body = ET.tostring(tree.getroot(), encoding="unicode")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + body + "\n"


def write_tm7(tree: ET.ElementTree, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_string(tree))
