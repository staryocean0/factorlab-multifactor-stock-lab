"""Canonical governed strategy-family registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class StrategyFamilyDefinition:
    """Project-level identity for a governed strategy family."""

    family_id: str
    display_name: str
    aliases: tuple[str, ...] = ()
    production_authority: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


GOVERNED_STRATEGY_FAMILY_DEFINITIONS: Final[tuple[StrategyFamilyDefinition, ...]] = (
    StrategyFamilyDefinition("t0", "T+0 intraday tradable assets"),
    StrategyFamilyDefinition("factor_rotation", "Multi-factor rotation"),
    StrategyFamilyDefinition("risk_off", "Risk-Off residual protection"),
    StrategyFamilyDefinition("filter_timing", "Filter timing / CloudRidge"),
    StrategyFamilyDefinition(
        "etf_lof_l0",
        "ETF/LOF dynamic label rotation",
        aliases=("etf_lof_dynamic_label_top1_rotation",),
    ),
)
GOVERNED_STRATEGY_FAMILIES: Final[tuple[str, ...]] = tuple(
    item.family_id for item in GOVERNED_STRATEGY_FAMILY_DEFINITIONS
)
_ALIAS_TO_FAMILY_ID: Final[dict[str, str]] = {
    alias: item.family_id
    for item in GOVERNED_STRATEGY_FAMILY_DEFINITIONS
    for alias in item.aliases
}


def canonical_strategy_family_id(value: object) -> str:
    """Return the canonical governed strategy-family id."""

    candidate = str(value or "").strip()
    return _ALIAS_TO_FAMILY_ID.get(candidate, candidate)


def is_governed_strategy_family(value: object) -> bool:
    """Return whether a value identifies a governed strategy family."""

    return canonical_strategy_family_id(value) in GOVERNED_STRATEGY_FAMILIES


def strategy_family_registry() -> tuple[dict[str, object], ...]:
    """Return registry entries as serializable dictionaries."""

    return tuple(item.to_dict() for item in GOVERNED_STRATEGY_FAMILY_DEFINITIONS)


__all__ = [
    "GOVERNED_STRATEGY_FAMILIES",
    "GOVERNED_STRATEGY_FAMILY_DEFINITIONS",
    "StrategyFamilyDefinition",
    "canonical_strategy_family_id",
    "is_governed_strategy_family",
    "strategy_family_registry",
]
