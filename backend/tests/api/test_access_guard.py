# ruff: noqa: F811
"""Zugriffsregel automatisch erzwingen (Review 2026-10-04, Punkt 5).

CLAUDE.md verlangt: jede Route mit `submission_id`/`placement_id`/`fee_id` im Pfad haengt
SubmissionAccess/PlacementAccess/FeeAccess an. Dieser Test macht daraus eine Pruefung: er liest
ALLE solchen Operationen aus dem OpenAPI-Schema der App und ruft jede mit den ECHTEN IDs eines
Prozesses auf, der einem anderen Nutzer gehoert - als Fremder (kein Admin, nicht im Team) muss
jede Operation 404 liefern. Eine neu vergessene Dependency faellt hier sofort auf, noch bevor
etwas live geht.

Warum Verhalten statt `app.routes`: In FastAPI 0.141 steht in `app.routes` nur ein verschachteltes
`_IncludedRouter`-Objekt, keine einzelnen Routen - ein Test darueber fande 0 Routen und waere
wirkungslos gruen. Die Zugriffs-Dependencies laufen vor der Body-Validierung, daher genuegt ein
leerer Body: ohne Schutz kaeme 422/200/400 statt 404.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from tests.api.test_team_lead import Person, Team, team  # noqa: F401

ID_NAMES = ("submission_id", "placement_id", "fee_id")
METHODS = ("get", "post", "put", "patch", "delete")

# Operationen, die ABSICHTLICH nicht mit 404 antworten duerfen - nur mit Begruendung eintragen.
# Format: (METHODE, Pfad-Schablone). Aktuell ist keine Ausnahme noetig.
ALLOWED_NON_404: dict[tuple[str, str], str] = {}


def _operations(client: TestClient) -> list[tuple[str, str, dict[str, Any]]]:
    paths: dict[str, Any] = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    found = []
    for path, item in paths.items():
        if not any("{" + name + "}" in path for name in ID_NAMES):
            continue
        for method in METHODS:
            if method in item:
                found.append((method.upper(), path, item[method]))
    return found


def _url(path: str, operation: dict[str, Any], real: dict[str, str]) -> str:
    url = path
    for parameter in operation.get("parameters", []):
        if parameter.get("in") != "path":
            continue
        name = parameter["name"]
        schema = parameter.get("schema", {})
        if name in real:
            value = real[name]
        elif schema.get("enum"):
            value = str(schema["enum"][0])
        elif schema.get("format") == "uuid":
            value = str(uuid.uuid4())
        else:
            value = "x"
        url = url.replace("{" + name + "}", value)
    return url


def _call(client: TestClient, method: str, url: str, headers: dict[str, str]) -> int:
    body = {} if method in ("POST", "PUT", "PATCH") else None
    return client.request(method, url, json=body, headers=headers).status_code


def test_every_id_route_hides_foreign_processes(client: TestClient, team: Team) -> None:  # noqa: F811
    owner, stranger = team.a, team.c  # C ist weder A noch im Team von A
    real = {
        "submission_id": owner.process_id,
        "placement_id": owner.placement_id,
        "fee_id": owner.fee_id,
    }
    operations = _operations(client)
    # Nicht wirkungslos: die Schablonen-Suche muss die bekannten 29 Operationen finden
    # (steigt mit neuen Routen, faellt nur bei einem Fehler der Suche).
    assert len(operations) >= 29, len(operations)

    leaks = []
    reachable_for_owner = 0
    for method, path, operation in operations:
        url = _url(path, operation, real)
        stranger_status = _call(client, method, url, stranger.headers)
        if stranger_status != 404 and (method, path) not in ALLOWED_NON_404:
            leaks.append((method, path, stranger_status))
        if _call(client, method, url, owner.headers) != 404:
            reachable_for_owner += 1
    assert not leaks, f"Routen ohne Zugriffspruefung (Fremder bekommt kein 404): {leaks}"
    # Gegenprobe: der Eigentuemer erreicht die meisten Operationen (sonst waere "404 fuer den
    # Fremden" nichts wert, z. B. weil die IDs im Test ins Leere zeigen).
    assert reachable_for_owner >= len(operations) // 2, reachable_for_owner


def test_nonexistent_ids_look_the_same_as_foreign_ones(client: TestClient, team: Team) -> None:  # noqa: F811
    """Fremd UND nicht existent: dasselbe 404 (kein Hinweis, ob es den Prozess gibt)."""
    ghosts = {name: str(uuid.uuid4()) for name in ID_NAMES}
    for method, path, operation in _operations(client):
        status = _call(client, method, _url(path, operation, ghosts), team.a.headers)
        assert status == 404, (method, path, status)
