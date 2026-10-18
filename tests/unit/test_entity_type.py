from pathlib import Path

import pytest

from breachlens.extract.entity_type import ORG, PERSON, classify_entity, load_entity_config

ROOT = Path(__file__).resolve().parents[2]
CFG = load_entity_config(ROOT / "config" / "entities.yaml")


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("HARBORLINE LOGISTICS INC", ORG),
        ("Brightline Office Supply LLC", ORG),
        ("RIVERBEND FAMILY CLINIC", ORG),
        ("CARNEY, ERIC D", PERSON),
        ("TIMOTHY VAN DYKE II", PERSON),
        ("COLEMAN, JUAN", PERSON),
        ("DR. KERRY M SMITH", PERSON),
        ("", PERSON),
    ],
)
def test_classify_entity(name, kind):
    assert classify_entity(name, CFG)[0] == kind


def test_reason_names_the_match():
    assert classify_entity("HARBORLINE LOGISTICS INC", CFG)[1] == "ORG_WORD:LOGISTICS"
    assert classify_entity("ACME HOLDINGS LLC", CFG)[1] == "ORG_SUFFIX:LLC"
