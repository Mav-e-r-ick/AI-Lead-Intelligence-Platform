"""Unit tests for message_generator.py."""

from __future__ import annotations

from datetime import datetime, timezone

from lead_intelligence.application.dto.inflection_models import (
    Inflection,
    InflectionReport,
    InflectionType,
)
from lead_intelligence.application.messaging.message_generator import (
    generate_message,
    generate_message_for_report,
)


def _fixed_clock() -> datetime:
    return datetime(2024, 6, 1, tzinfo=timezone.utc)


def _inflection(
    inflection_type: InflectionType, confidence: float = 0.85
) -> Inflection:
    return Inflection(
        type=inflection_type,
        confidence=confidence,
        supporting_comparisons=(),
        explanation="test",
        detected_at=_fixed_clock(),
        rule_id="INF-000",
    )


class TestGenerateMessage:
    def test_promotion_message_mentions_name_title_and_company(self) -> None:
        message = generate_message(
            "Ada Lovelace", "Acme Corp", "CEO", _inflection(InflectionType.PROMOTION)
        )

        assert "Ada Lovelace" in message
        assert "Acme Corp" in message
        assert "CEO" in message
        assert "promotion" in message.lower()

    def test_missing_company_falls_back_to_generic_phrase(self) -> None:
        message = generate_message(
            "Ada Lovelace", None, "CEO", _inflection(InflectionType.PROMOTION)
        )

        assert "None" not in message
        assert "your company" in message

    def test_missing_title_falls_back_to_generic_phrase(self) -> None:
        message = generate_message(
            "Ada Lovelace", "Acme Corp", None, _inflection(InflectionType.PROMOTION)
        )

        assert "None" not in message
        assert "your new role" in message

    def test_every_inflection_type_produces_a_non_empty_message(self) -> None:
        for inflection_type in InflectionType:
            message = generate_message(
                "Ada Lovelace", "Acme Corp", "CEO", _inflection(inflection_type)
            )
            assert message
            assert "Ada Lovelace" in message

    def test_possible_resignation_message_is_not_congratulatory(self) -> None:
        message = generate_message(
            "Ada Lovelace",
            "Acme Corp",
            None,
            _inflection(InflectionType.POSSIBLE_RESIGNATION),
        )

        assert "congratulations" not in message.lower()


class TestGenerateMessageForReport:
    def test_no_report_yields_no_message(self) -> None:
        assert generate_message_for_report(None, "Ada Lovelace", "Acme", "CEO") is None

    def test_no_inflections_yields_no_message(self) -> None:
        report = InflectionReport(
            record_reference="row:1", inflections=(), generated_at=_fixed_clock()
        )

        assert generate_message_for_report(report, "Ada Lovelace", "Acme", "CEO") is None

    def test_picks_the_strongest_inflection(self) -> None:
        weaker = _inflection(InflectionType.CONTACT_INFO_CHANGED, confidence=0.5)
        stronger = _inflection(InflectionType.PROMOTION, confidence=0.9)
        report = InflectionReport(
            record_reference="row:1",
            inflections=(weaker, stronger),
            generated_at=_fixed_clock(),
        )

        message = generate_message_for_report(report, "Ada Lovelace", "Acme", "CEO")

        assert message is not None
        assert "promotion" in message.lower()

    def test_single_inflection_produces_a_message(self) -> None:
        report = InflectionReport(
            record_reference="row:1",
            inflections=(_inflection(InflectionType.COMPANY_CHANGE),),
            generated_at=_fixed_clock(),
        )

        message = generate_message_for_report(report, "Ada Lovelace", "Acme", "CTO")

        assert message is not None
        assert "Ada Lovelace" in message
