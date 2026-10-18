"""PERSON vs ORG for names found in person fields (`config/entities.yaml`).

Tax and health forms always carry employer / payer / provider names, and a person field
sometimes holds an organization (P21). Those names go to `excluded_entities`.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

PERSON, ORG = "PERSON", "ORG"


class EntityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    org_suffixes: list[str]
    org_words: list[str]


def load_entity_config(path: Path) -> EntityConfig:
    with path.open(encoding="utf-8") as fh:
        return EntityConfig.model_validate(yaml.safe_load(fh))


def classify_entity(name: str, cfg: EntityConfig) -> tuple[str, str]:
    """(PERSON | ORG, reason). Reason names the matching org word or suffix."""
    words = re.sub(r"[^A-Z0-9 ]", " ", name.upper()).split()
    if not words:
        return PERSON, ""
    joined = " ".join(words)
    for w in cfg.org_words:
        if re.search(r"(?<![A-Z])" + re.escape(w) + r"(?![A-Z])", joined):
            return ORG, f"ORG_WORD:{w}"
    if words[-1] in cfg.org_suffixes:
        return ORG, f"ORG_SUFFIX:{words[-1]}"
    return PERSON, ""
