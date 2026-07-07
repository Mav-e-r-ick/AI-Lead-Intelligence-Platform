"""Unit tests for IdentityResolutionProfile / SignalTypeDefinition."""

from __future__ import annotations

import pytest

from lead_intelligence.application.dto.identity_resolution_models import SignalTier
from lead_intelligence.application.identity_resolution.config import (
    IdentityResolutionProfile,
    SignalTypeDefinition,
    default_profile,
)
from lead_intelligence.domain.exceptions import (
    InvalidIdentityResolutionConfigurationError,
)


def test_default_profile_validates_cleanly() -> None:
    default_profile().validate()


def test_definition_for_unknown_signal_type_raises() -> None:
    profile = default_profile()

    with pytest.raises(InvalidIdentityResolutionConfigurationError):
        profile.definition_for("not_a_real_signal_type")


def test_empty_signal_definitions_is_invalid() -> None:
    profile = IdentityResolutionProfile(name="t", signal_definitions={})

    with pytest.raises(InvalidIdentityResolutionConfigurationError):
        profile.validate()


def test_candidate_review_threshold_above_auto_merge_threshold_is_invalid() -> None:
    profile = IdentityResolutionProfile(
        name="t", auto_merge_threshold=0.5, candidate_review_threshold=0.9
    )

    with pytest.raises(InvalidIdentityResolutionConfigurationError):
        profile.validate()


def test_zero_candidate_review_threshold_is_invalid() -> None:
    profile = IdentityResolutionProfile(name="t", candidate_review_threshold=0.0)

    with pytest.raises(InvalidIdentityResolutionConfigurationError):
        profile.validate()


def test_negative_contradiction_penalty_is_invalid() -> None:
    profile = IdentityResolutionProfile(name="t", contradiction_penalty=-0.1)

    with pytest.raises(InvalidIdentityResolutionConfigurationError):
        profile.validate()


def test_min_independent_signals_below_one_is_invalid() -> None:
    profile = IdentityResolutionProfile(
        name="t", min_independent_signals_without_strong_match=0
    )

    with pytest.raises(InvalidIdentityResolutionConfigurationError):
        profile.validate()


def test_max_candidates_considered_below_one_is_invalid() -> None:
    profile = IdentityResolutionProfile(name="t", max_candidates_considered=0)

    with pytest.raises(InvalidIdentityResolutionConfigurationError):
        profile.validate()


def test_weight_outside_unit_interval_is_invalid() -> None:
    profile = IdentityResolutionProfile(
        name="t",
        signal_definitions={
            "bogus": SignalTypeDefinition(tier=SignalTier.WEAK, weight=1.5)
        },
    )

    with pytest.raises(InvalidIdentityResolutionConfigurationError):
        profile.validate()


def test_signal_definitions_mapping_is_immutable() -> None:
    profile = default_profile()

    with pytest.raises(TypeError):
        profile.signal_definitions["new"] = SignalTypeDefinition(  # type: ignore[index]
            tier=SignalTier.WEAK, weight=0.1
        )
