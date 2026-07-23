"""Localized, player-facing explanations for controllable policy levers.

The Registry remains authoritative for validation and execution.  Translation
catalogs are data resources so clients and future native engines can reuse the
same economics copy without embedding a display language in executable code.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.resources import files
import json
from typing import Any


DEFAULT_PLAYER_LOCALE = "zh_CN"
AVAILABLE_POLICY_LOCALES = frozenset({DEFAULT_PLAYER_LOCALE})
EXPLANATION_FIELDS = frozenset({"meaning", "mechanics", "tradeoffs", "watch"})


@dataclass(frozen=True)
class PolicyExplanation:
    meaning: str
    mechanics: str
    tradeoffs: str
    watch: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def load_policy_explanations(
    locale: str = DEFAULT_PLAYER_LOCALE,
) -> dict[str, PolicyExplanation]:
    """Load and validate one packaged policy-explanation catalog."""
    if locale not in AVAILABLE_POLICY_LOCALES:
        raise ValueError(f"unsupported policy explanation locale {locale!r}")
    resource = files("macro_sim").joinpath(
        "data", "locales", locale, "policy_explanations.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        payload: Any = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("policy explanation catalog must be an object")

    result: dict[str, PolicyExplanation] = {}
    for lever, raw in payload.items():
        if not isinstance(lever, str) or not lever:
            raise ValueError("policy explanation keys must be non-empty strings")
        if not isinstance(raw, dict) or set(raw) != EXPLANATION_FIELDS:
            raise ValueError(
                f"policy explanation {lever!r} has missing or unknown fields"
            )
        if any(not isinstance(raw[name], str) or not raw[name].strip()
               for name in EXPLANATION_FIELDS):
            raise ValueError(
                f"policy explanation {lever!r} fields must be non-empty strings"
            )
        result[lever] = PolicyExplanation(
            meaning=raw["meaning"],
            mechanics=raw["mechanics"],
            tradeoffs=raw["tradeoffs"],
            watch=raw["watch"],
        )
    return result


POLICY_EXPLANATIONS = load_policy_explanations()
