"""Unit tests for fact_extraction.extract_facts — every rule-based
pattern's fire and no-fire behavior."""

from __future__ import annotations

from lead_intelligence.infrastructure.search.extraction.fact_extraction import (
    NO_FACTS,
    extract_facts,
)


class TestAppointedPattern:
    def test_headline_named_role_of_company(self) -> None:
        facts = extract_facts("Ada Lovelace named CTO of Acme Corp", "")

        assert facts.full_name == "Ada Lovelace"
        assert facts.title == "CTO"
        assert facts.company_name == "Acme Corp"
        assert facts.matched_pattern == "FACT-001-appointed-role-of-company"

    def test_prose_has_been_appointed(self) -> None:
        facts = extract_facts(
            "",
            "Acme Corp announced today that Ada Lovelace has been appointed "
            "Chief Technology Officer of Acme Corp.",
        )

        assert facts.full_name == "Ada Lovelace"
        assert facts.title == "Chief Technology Officer"
        assert facts.company_name == "Acme Corp"

    def test_appointed_as_its_variant(self) -> None:
        facts = extract_facts(
            "", "Ada Lovelace was appointed as its Chief Executive Officer at Acme."
        )

        assert facts.title == "Chief Executive Officer"
        assert facts.company_name == "Acme"


class TestPromotedPattern:
    def test_promoted_to_role_at_company(self) -> None:
        facts = extract_facts(
            "", "Ada Lovelace was promoted to Chief Executive Officer at Acme Corp."
        )

        assert facts.full_name == "Ada Lovelace"
        assert facts.title == "Chief Executive Officer"
        assert facts.company_name == "Acme Corp"
        assert facts.matched_pattern == "FACT-002-promoted-to-role-of-company"

    def test_promoted_to_role_without_company(self) -> None:
        facts = extract_facts("", "Ada Lovelace was promoted to Senior Vice President.")

        assert facts.full_name == "Ada Lovelace"
        assert facts.title == "Senior Vice President"
        assert facts.company_name is None
        assert facts.matched_pattern == "FACT-005-promoted-to-role"


class TestJoinsPattern:
    def test_joins_company_as_role(self) -> None:
        facts = extract_facts(
            "", "Ada Lovelace joins Coatue Management as Chief Data Officer."
        )

        assert facts.full_name == "Ada Lovelace"
        assert facts.company_name == "Coatue Management"
        assert facts.title == "Chief Data Officer"
        assert facts.matched_pattern == "FACT-003-joins-company-as-role"

    def test_has_joined_variant(self) -> None:
        facts = extract_facts("", "Grace Hopper has joined Contoso as its President.")

        assert facts.full_name == "Grace Hopper"
        assert facts.company_name == "Contoso"
        assert facts.title == "President"


class TestCommaBylinePattern:
    def test_name_comma_role_of_company(self) -> None:
        facts = extract_facts(
            "",
            "We spoke with Ada Lovelace, Chief Technology Officer of Acme Corp, "
            "about the road ahead.",
        )

        assert facts.full_name == "Ada Lovelace"
        assert facts.title == "Chief Technology Officer"
        assert facts.company_name == "Acme Corp"
        assert facts.matched_pattern == "FACT-004-name-comma-role-of-company"


class TestScanOrderAndNoMatch:
    def test_title_is_scanned_before_visible_text(self) -> None:
        facts = extract_facts(
            "Grace Hopper named CEO of Contoso",
            "Ada Lovelace joins Acme Corp as CTO.",
        )

        assert facts.full_name == "Grace Hopper"

    def test_text_is_scanned_when_title_yields_nothing(self) -> None:
        facts = extract_facts(
            "Weekly industry roundup", "Ada Lovelace joins Acme Corp as CTO."
        )

        assert facts.full_name == "Ada Lovelace"

    def test_no_pattern_match_returns_no_facts(self) -> None:
        facts = extract_facts(
            "Weather forecast", "Sunny with a chance of rain tomorrow."
        )

        assert facts == NO_FACTS
        assert facts.matched_pattern is None

    def test_empty_inputs_return_no_facts(self) -> None:
        assert extract_facts("", "") == NO_FACTS

    def test_lowercase_prose_never_matches_a_name(self) -> None:
        facts = extract_facts("", "someone was appointed manager of the store.")

        # No announcement-pattern (name/title/company) match — event_keywords
        # is independent of that match, same as email/phone/linkedin_url (see
        # module docstring), and legitimately detects "appointed" here.
        assert facts.full_name is None
        assert facts.title is None
        assert facts.company_name is None
        assert facts.matched_pattern is None
        assert facts.event_keywords == "appointment"


class TestDeterminism:
    def test_same_input_always_yields_the_same_facts(self) -> None:
        text = "Ada Lovelace joins Acme Corp as Chief Technology Officer."

        first = extract_facts("", text)
        second = extract_facts("", text)

        assert first == second


class TestContactFactsAreIndependentOfAnnouncementPatterns:
    """email/phone/linkedin_url are found regardless of whether any of the
    five announcement patterns also matched — see module docstring."""

    def test_email_found_on_a_page_with_no_announcement_pattern(self) -> None:
        facts = extract_facts(
            "Leadership", "Ada Lovelace, CEO. Contact: ada@acme.com"
        )

        assert facts.matched_pattern is None
        assert facts.email == "ada@acme.com"

    def test_phone_found_on_a_page_with_no_announcement_pattern(self) -> None:
        facts = extract_facts("Leadership", "Ada Lovelace, CEO. Call +1 415-555-0134.")

        assert facts.matched_pattern is None
        assert facts.phone == "+1 415-555-0134"

    def test_linkedin_url_found_on_a_page_with_no_announcement_pattern(self) -> None:
        facts = extract_facts(
            "Leadership", "Ada Lovelace, CEO. https://www.linkedin.com/in/ada-lovelace"
        )

        assert facts.matched_pattern is None
        assert facts.linkedin_url == "https://www.linkedin.com/in/ada-lovelace"

    def test_all_three_extracted_alongside_a_matched_announcement_pattern(
        self,
    ) -> None:
        facts = extract_facts(
            "",
            "Ada Lovelace was appointed CTO of Acme Corp. Reach her at "
            "ada@acme.com or +1 415-555-0134, or on "
            "https://linkedin.com/in/ada-lovelace.",
        )

        assert facts.matched_pattern is not None
        assert facts.full_name == "Ada Lovelace"
        assert facts.email == "ada@acme.com"
        assert facts.phone == "+1 415-555-0134"
        assert facts.linkedin_url == "https://linkedin.com/in/ada-lovelace"

    def test_no_contact_details_present_yields_none_for_all_three(self) -> None:
        facts = extract_facts("Weather forecast", "Sunny with a chance of rain.")

        assert facts.email is None
        assert facts.phone is None
        assert facts.linkedin_url is None


class TestEventKeywords:
    """event_keywords is independent of an announcement-pattern match —
    same reasoning as email/phone/linkedin_url (see module docstring)."""

    def test_promotion_keyword_is_detected(self) -> None:
        facts = extract_facts("", "Ada Lovelace was promoted to CTO.")

        assert facts.event_keywords == "promotion"

    def test_multiple_keywords_are_all_reported_comma_joined(self) -> None:
        facts = extract_facts(
            "", "Ada Lovelace was appointed to the board after being named CEO."
        )

        assert facts.event_keywords == "appointment, board, named"

    def test_resignation_keyword_is_detected(self) -> None:
        facts = extract_facts("", "Ada Lovelace resigned as CTO of Acme Corp.")

        assert facts.event_keywords == "resignation"

    def test_retirement_keyword_is_detected(self) -> None:
        facts = extract_facts("", "Ada Lovelace announced her retirement.")

        assert facts.event_keywords == "retirement"

    def test_steps_down_multi_word_keyword_is_detected(self) -> None:
        facts = extract_facts("", "Ada Lovelace steps down as CEO.")

        assert facts.event_keywords == "steps_down"

    def test_acquisition_keyword_is_detected(self) -> None:
        facts = extract_facts("", "Acme Corp was acquired by Globex.")

        assert facts.event_keywords == "acquisition"

    def test_title_is_scanned_alongside_visible_text(self) -> None:
        facts = extract_facts("Ada Lovelace Promoted to CEO", "")

        assert facts.event_keywords == "promotion"

    def test_unrelated_text_yields_none(self) -> None:
        facts = extract_facts("Weather forecast", "Sunny with a chance of rain.")

        assert facts.event_keywords is None

    def test_present_alongside_a_matched_announcement_pattern(self) -> None:
        facts = extract_facts("", "Ada Lovelace was appointed CTO of Acme Corp.")

        assert facts.matched_pattern is not None
        assert facts.event_keywords == "appointment"
