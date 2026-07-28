"""Codex subscription model metadata and reasoning-control contracts."""

import pytest

from src.chatgpt_subscription import (
    default_reasoning_effort,
    normalize_reasoning_effort,
    supported_reasoning_efforts,
)


def test_gpt56_profiles_expose_single_request_efforts_without_ultra():
    assert supported_reasoning_efforts("gpt-5.6-sol") == [
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    assert "ultra" not in supported_reasoning_efforts("gpt-5.6-terra")


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-5.6-sol", "low"),
        ("gpt-5.6-terra", "medium"),
        ("gpt-5.6-luna", "medium"),
        ("gpt-5.5", "medium"),
        ("other-model", None),
    ],
)
def test_subscription_model_defaults(model, expected):
    assert default_reasoning_effort(model) == expected


def test_reasoning_effort_normalization_is_model_scoped():
    assert normalize_reasoning_effort("gpt-5.6-sol", " MAX ") == "max"
    assert normalize_reasoning_effort("gpt-5.5", "max") is None
    assert normalize_reasoning_effort("gpt-5.6-sol", "ultra") is None
    assert normalize_reasoning_effort("other-model", "high") is None
    assert normalize_reasoning_effort("gpt-5.6-sol", "auto") is None
