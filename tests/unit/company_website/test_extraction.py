"""Unit tests for extract_executives."""

from __future__ import annotations

from lead_intelligence.infrastructure.enrichment.company_website.extraction import (
    extract_executives,
)

_LONG_BIO = (
    "Ada has led the company for ten years, driving growth and innovation "
    "across every product line the company ships worldwide."
)


def test_extracts_name_title_biography_email_and_phone() -> None:
    html = f"""
    <html><body>
      <div class="team-member">
        <h2 class="name">Ada Lovelace</h2>
        <p class="title">Chief Executive Officer</p>
        <p>{_LONG_BIO}</p>
        <a href="mailto:ada@acme.com">Email</a>
        <a href="tel:+15551234567">Call</a>
      </div>
    </body></html>
    """

    executives = extract_executives(html)

    assert len(executives) == 1
    executive = executives[0]
    assert executive.name == "Ada Lovelace"
    assert executive.title == "Chief Executive Officer"
    assert executive.biography == _LONG_BIO
    assert executive.email == "ada@acme.com"
    assert executive.phone == "+15551234567"


def test_extracts_multiple_people_from_one_page() -> None:
    html = """
    <html><body>
      <div class="team-member">
        <h2 class="name">Ada Lovelace</h2>
        <p class="title">CEO</p>
      </div>
      <div class="team-member">
        <h2 class="name">Grace Hopper</h2>
        <p class="title">CTO</p>
      </div>
    </body></html>
    """

    executives = extract_executives(html)

    assert [e.name for e in executives] == ["Ada Lovelace", "Grace Hopper"]
    assert [e.title for e in executives] == ["CEO", "CTO"]


def test_missing_title_and_biography_are_none_not_errors() -> None:
    html = """
    <html><body>
      <div class="team-member">
        <h2 class="name">Ada Lovelace</h2>
      </div>
    </body></html>
    """

    executives = extract_executives(html)

    assert executives[0].name == "Ada Lovelace"
    assert executives[0].title is None
    assert executives[0].biography is None
    assert executives[0].email is None
    assert executives[0].phone is None


def test_email_falls_back_to_regex_when_no_mailto_link() -> None:
    html = """
    <html><body>
      <div class="team-member">
        <h2 class="name">Ada Lovelace</h2>
        <p>Reach her at ada@acme.com for press inquiries.</p>
      </div>
    </body></html>
    """

    executives = extract_executives(html)

    assert executives[0].email == "ada@acme.com"


def test_phone_falls_back_to_regex_when_no_tel_link() -> None:
    html = """
    <html><body>
      <div class="team-member">
        <h2 class="name">Ada Lovelace</h2>
        <p>Call the office at 555-123-4567 for scheduling.</p>
      </div>
    </body></html>
    """

    executives = extract_executives(html)

    assert executives[0].phone is not None
    assert "555" in executives[0].phone


def test_page_with_no_matching_containers_returns_empty() -> None:
    html = "<html><body><p>Welcome to our homepage.</p></body></html>"

    executives = extract_executives(html)

    assert executives == ()


def test_container_without_a_name_is_skipped() -> None:
    html = """
    <html><body>
      <div class="team-member">
        <p class="title">Just a title, no name heading or name element.</p>
      </div>
    </body></html>
    """

    executives = extract_executives(html)

    assert executives == ()


def test_duplicate_name_and_title_pairs_are_deduplicated() -> None:
    html = """
    <html><body>
      <div class="team-member">
        <h2 class="name">Ada Lovelace</h2>
        <p class="title">CEO</p>
      </div>
      <div class="staff-bio">
        <h2 class="name">Ada Lovelace</h2>
        <p class="title">CEO</p>
      </div>
    </body></html>
    """

    executives = extract_executives(html)

    assert len(executives) == 1


def test_innermost_container_is_used_not_the_outer_wrapper() -> None:
    html = """
    <section class="leadership-team">
      <div class="team-member">
        <h2 class="name">Ada Lovelace</h2>
        <p class="title">CEO</p>
      </div>
      <div class="team-member">
        <h2 class="name">Grace Hopper</h2>
        <p class="title">CTO</p>
      </div>
    </section>
    """

    executives = extract_executives(html)

    assert len(executives) == 2


def test_short_paragraph_is_not_treated_as_biography() -> None:
    html = """
    <html><body>
      <div class="team-member">
        <h2 class="name">Ada Lovelace</h2>
        <p class="title">CEO</p>
        <p>Short.</p>
      </div>
    </body></html>
    """

    executives = extract_executives(html)

    assert executives[0].biography is None
