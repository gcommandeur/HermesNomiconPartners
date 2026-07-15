from cc_crm.integrations.bullhorn import BullhornClient


def test_normalize_candidate_maps_bullhorn_fields() -> None:
    record = {
        "firstName": "Anna",
        "lastName": "Beispiel",
        "email": "anna@example.com",
        "mobile": "+49 151 1234567",
        "occupation": "Steuerberater/in",
        "city": "Muenchen",
        "zip": "80331",
        "desiredSalary": 85000,
    }

    normalized = BullhornClient.normalize_candidate(record)

    assert normalized["first_name"] == "Anna"
    assert normalized["last_name"] == "Beispiel"
    assert normalized["email"] == "anna@example.com"
    assert normalized["job_title"] == "Steuerberater/in"
    assert normalized["salary_expectation"] == "85000"


def test_normalize_candidate_handles_missing_optional_fields() -> None:
    normalized = BullhornClient.normalize_candidate({"firstName": "Tom", "lastName": "Muster"})

    assert normalized["email"] is None
    assert normalized["salary_expectation"] is None


def test_normalize_client_maps_address() -> None:
    record = {
        "name": "Kanzlei Weber",
        "email": "kontakt@kanzlei-weber.example.com",
        "phone": "+49 89 1234567",
        "url": "https://kanzlei-weber.example.com",
        "address": {"city": "Muenchen", "zip": "80331"},
        "companyDescription": "Steuerberatung",
    }

    normalized = BullhornClient.normalize_client(record)

    assert normalized["name"] == "Kanzlei Weber"
    assert normalized["city"] == "Muenchen"
    assert normalized["postal_code"] == "80331"
