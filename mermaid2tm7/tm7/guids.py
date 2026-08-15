"""Deterministic Guids for TM7 elements and flows.

Implements ``docs/04-tm7-mapping-spec.md`` §Guid stability. Guids are derived with
UUIDv5 from a fixed namespace so regenerating a TM7 after a Markdown edit produces
a minimal diff, and threat state recorded against an element survives regeneration.

NOTE (compatibility): the spec says to check the existing ``tm7_cli.py`` generator
first — if it already emits Guids by some scheme, keep it, because changing it is a
compatibility event for existing models. That generator is not present in this
repository, so this module defines the scheme; when integrating, reconcile with the
skill's ``update-threats`` round-tripping before shipping. See ``docs/investigation.md``.
"""

from __future__ import annotations

import uuid

# Fixed namespace for this tool. Do not change without a compatibility migration.
GUID_NS = uuid.UUID("6b9d0d9e-4c3a-5f21-9a7e-2f1c8d3b4a56")


def element_guid(model_id: str, element_id: str) -> str:
    return str(uuid.uuid5(GUID_NS, f"{model_id}:{element_id}"))


def flow_guid(model_id: str, source_id: str, target_id: str, ordinal: int = 0) -> str:
    return str(uuid.uuid5(GUID_NS, f"{model_id}:{source_id}->{target_id}:{ordinal}"))


def boundary_guid(model_id: str, boundary_id: str) -> str:
    return str(uuid.uuid5(GUID_NS, f"{model_id}:boundary:{boundary_id}"))
