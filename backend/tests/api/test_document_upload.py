from fastapi.testclient import TestClient

from cc_crm.core.config import get_settings


def _create_candidate(client: TestClient) -> str:
    payload = {"candidate_number": "9002", "first_name": "Test", "last_name": "Kandidat"}
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201
    return str(response.json()["id"])


def test_upload_rejects_disallowed_extension(client: TestClient) -> None:
    candidate_id = _create_candidate(client)

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("malware.exe", b"irrelevant", "application/octet-stream")},
    )

    assert response.status_code == 415
    assert "erlaubt" in response.json()["detail"].lower()


def test_upload_rejects_mismatched_content_type(client: TestClient) -> None:
    candidate_id = _create_candidate(client)

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("cv.pdf", b"irrelevant", "text/plain")},
    )

    assert response.status_code == 415


def test_upload_rejects_file_over_size_limit(client: TestClient) -> None:
    candidate_id = _create_candidate(client)
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    oversized_content = b"a" * (max_bytes + 1)

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("cv.pdf", oversized_content, "application/pdf")},
    )

    assert response.status_code == 413
    assert (
        "groß" in response.json()["detail"].lower() or "gross" in response.json()["detail"].lower()
    )


def test_upload_accepts_normal_pdf(client: TestClient) -> None:
    candidate_id = _create_candidate(client)

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("cv.pdf", b"%PDF-1.4 dummy content", "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["content_type"] == "application/pdf"


def test_cv_upload_is_named_after_last_and_first_name(client: TestClient) -> None:
    """CV-Dokumente ("Schnelle Submission"-Auftrag, Dateibenennung
    vereinheitlichen): "CV_NACHNAME.VORNAME" + Endung, UNABHAENGIG vom
    Originaldateinamen und unabhaengig von der candidate_number - siehe
    services/storage.py::cv_upload_filename. Loest fuer document_type=="cv"
    die aeltere Kandidaten-Nr.-Konvention ab (die fuer andere Dokumenttypen
    unveraendert weitergilt, siehe test_second_non_cv_candidate_document_
    gets_type_suffix_and_renames_sibling unten)."""
    candidate_id = _create_candidate(client)

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("ganz-anderer-name.pdf", b"%PDF-1.4 dummy content", "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "CV_Kandidat.Test.pdf"
    assert body["storage_key"].endswith("/CV_Kandidat.Test.pdf")


def test_second_cv_upload_gets_a_counter_and_does_not_rename_the_first(
    client: TestClient,
) -> None:
    """Regressionsschutz fuer den auf Produktion bestaetigten Fall (Kandidat
    1823, Simon Kroll: zwei CV-Dokumente durch Re-Upload): der ZWEITE
    CV-Upload bekommt einen fortlaufenden Zaehler ("..._2.pdf") - anders als
    bei der Kandidaten-Nr.-Konvention (siehe unten) wird das erste CV dabei
    NICHT umbenannt, da die CV-Konvention nicht von einer Typ-Zusatz-
    Umstellung abhaengt."""
    candidate_id = _create_candidate(client)

    first = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("cv.pdf", b"%PDF-1.4 first", "application/pdf")},
    )
    assert first.status_code == 201
    assert first.json()["filename"] == "CV_Kandidat.Test.pdf"

    second = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "cv"},
        files={"file": ("cv-neu.pdf", b"%PDF-1.4 second", "application/pdf")},
    )
    assert second.status_code == 201
    assert second.json()["filename"] == "CV_Kandidat.Test_2.pdf"

    documents = client.get(
        "/api/v1/documents", params={"owner_type": "candidate", "owner_id": candidate_id}
    ).json()
    filenames = sorted(document["filename"] for document in documents)
    assert filenames == ["CV_Kandidat.Test.pdf", "CV_Kandidat.Test_2.pdf"]


def test_non_cv_candidate_upload_is_still_named_after_candidate_number(
    client: TestClient,
) -> None:
    """Die neue CV-Konvention gilt NUR fuer document_type=="cv" - andere
    Kandidaten-Dokumenttypen (z.B. Vertraege) bleiben bei der bestehenden
    Kandidaten-Nr.-Konvention (siehe services/storage.py::
    plan_new_candidate_document)."""
    candidate_id = _create_candidate(client)

    response = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "contract"},
        files={"file": ("vertrag.pdf", b"%PDF-1.4 dummy content", "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "9002.pdf"
    assert body["storage_key"].endswith("/9002.pdf")


def test_second_non_cv_candidate_document_gets_type_suffix_and_renames_sibling(
    client: TestClient,
) -> None:
    """Regressionsschutz fuer den ZWEITEN Nicht-CV-Dokumenttyp desselben
    Kandidaten: sowohl das neue als auch das zuvor "nackt" benannte erste
    Dokument werden konsistent auf die Typ-Zusatz-Konvention umgestellt,
    ohne dass beide auf denselben Namen kollidieren (gleicher Mechanismus
    wie vor der CV-spezifischen Ausnahme, nur jetzt mit document_type
    "contract" statt "cv" belegt)."""
    candidate_id = _create_candidate(client)

    first = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "contract"},
        files={"file": ("vertrag.pdf", b"%PDF-1.4 first", "application/pdf")},
    )
    assert first.status_code == 201
    assert first.json()["filename"] == "9002.pdf"

    second = client.post(
        "/api/v1/documents/upload",
        data={"owner_type": "candidate", "owner_id": candidate_id, "document_type": "contract"},
        files={"file": ("vertrag-neu.pdf", b"%PDF-1.4 second", "application/pdf")},
    )
    assert second.status_code == 201
    assert second.json()["filename"] == "9002_contract_2.pdf"

    documents = client.get(
        "/api/v1/documents", params={"owner_type": "candidate", "owner_id": candidate_id}
    ).json()
    filenames = sorted(document["filename"] for document in documents)
    assert filenames == ["9002_contract.pdf", "9002_contract_2.pdf"]


def test_non_candidate_upload_keeps_random_hash_naming(client: TestClient) -> None:
    """Die Kandidaten-Nr.-Konvention gilt bewusst nur fuer owner_type
    "candidate" - andere Owner (Kanzleien, Prozesse, ...) haben kein
    aequivalentes Nummernfeld und behalten das bisherige, kollisionssichere
    Zufalls-Namensschema."""
    client_company = client.post(
        "/api/v1/clients", json={"name": "Test Kanzlei GmbH"}
    )
    assert client_company.status_code == 201
    client_company_id = client_company.json()["id"]

    response = client.post(
        "/api/v1/documents/upload",
        data={
            "owner_type": "client",
            "owner_id": client_company_id,
            "document_type": "contract",
        },
        files={"file": ("vertrag.pdf", b"%PDF-1.4 dummy content", "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "vertrag.pdf"
    assert "_vertrag.pdf" in body["storage_key"]
