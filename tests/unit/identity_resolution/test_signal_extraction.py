"""Unit tests for signal_extraction.extract_identity."""

from __future__ import annotations

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.dto.identity_resolution_models import SubjectType
from lead_intelligence.application.identity_resolution.config import default_profile
from lead_intelligence.application.identity_resolution.signal_extraction import (
    extract_identity,
)
from tests.unit.identity_resolution.fixtures import make_cleaned_record

PROFILE = default_profile()


def test_person_extraction_picks_up_email_name_phone_title() -> None:
    record = make_cleaned_record(
        1,
        **{
            fc.PRIMARY_EMAIL: "Ada@Example.com",
            fc.FIRST_NAME: "Ada",
            fc.LAST_NAME: "Lovelace",
            fc.PRIMARY_PHONE: "+15551234567",
            fc.TITLE: "CEO",
        },
    )

    extracted = extract_identity(record, SubjectType.PERSON, "row:1", PROFILE)

    assert extracted.signal_types() == {"email_exact", "full_name", "phone", "title"}
    email_signal = next(s for s in extracted.signals if s.signal_type == "email_exact")
    assert email_signal.value == "ada@example.com"


def test_person_extraction_falls_back_to_email_and_direct_phone_fields() -> None:
    record = make_cleaned_record(
        2, **{fc.EMAIL: "bob@example.com", fc.DIRECT_PHONE: "+15550000000"}
    )

    extracted = extract_identity(record, SubjectType.PERSON, "row:2", PROFILE)

    assert extracted.signal_types() == {"email_exact", "phone"}


def test_person_extraction_falls_back_to_company_email_when_email_missing() -> None:
    record = make_cleaned_record(3, **{fc.COMPANY_EMAIL: "info@example.com"})

    extracted = extract_identity(record, SubjectType.PERSON, "row:3", PROFILE)

    assert extracted.signal_types() == {"email_exact"}


def test_person_extraction_skips_missing_fields_without_raising() -> None:
    record = make_cleaned_record(4)

    extracted = extract_identity(record, SubjectType.PERSON, "row:4", PROFILE)

    assert extracted.signals == ()


def test_full_name_signal_present_with_only_first_name() -> None:
    record = make_cleaned_record(5, **{fc.FIRST_NAME: "Ada"})

    extracted = extract_identity(record, SubjectType.PERSON, "row:5", PROFILE)

    name_signal = next(s for s in extracted.signals if s.signal_type == "full_name")
    assert name_signal.value == "ada"


def test_company_extraction_picks_up_duns_domain_and_city() -> None:
    record = make_cleaned_record(
        6,
        **{
            fc.DUNS_NUMBER: "001234567",
            fc.COMPANY_NAME: "Acme Corp",
            fc.PRIMARY_EMAIL: "exec@www.acme.com",
            fc.CITY: "Springfield",
        },
    )

    extracted = extract_identity(record, SubjectType.COMPANY, "row:6", PROFILE)

    assert extracted.signal_types() == {
        "duns_number",
        "company_domain_and_name",
        "company_name_city",
    }
    duns_signal = next(s for s in extracted.signals if s.signal_type == "duns_number")
    assert duns_signal.value == "001234567"


def test_company_domain_signal_strips_leading_www() -> None:
    record = make_cleaned_record(
        7, **{fc.COMPANY_NAME: "Acme Corp", fc.PRIMARY_EMAIL: "exec@www.acme.com"}
    )

    extracted = extract_identity(record, SubjectType.COMPANY, "row:7", PROFILE)

    domain_signal = next(
        s for s in extracted.signals if s.signal_type == "company_domain_and_name"
    )
    assert domain_signal.value == "acme.com|acme corp"


def test_company_extraction_omits_domain_signal_without_email() -> None:
    record = make_cleaned_record(
        8, **{fc.COMPANY_NAME: "Acme Corp", fc.CITY: "Springfield"}
    )

    extracted = extract_identity(record, SubjectType.COMPANY, "row:8", PROFILE)

    assert extracted.signal_types() == {"company_name_city"}


def test_record_reference_and_subject_type_are_carried_through() -> None:
    record = make_cleaned_record(9, **{fc.TITLE: "CTO"})

    extracted = extract_identity(record, SubjectType.PERSON, "row:9", PROFILE)

    assert extracted.record_reference == "row:9"
    assert extracted.subject_type is SubjectType.PERSON
