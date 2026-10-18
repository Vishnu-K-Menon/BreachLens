from collections import Counter
from datetime import timedelta
from pathlib import Path

import pytest

from breachlens.synth import identifiers as ids
from breachlens.synth.people import (
    BASE,
    DEPENDENT,
    EXTRA,
    EXTRA_GUARDIAN,
    STUDENT,
    build_population,
    check_reuse_cap,
    read_pool,
    shared_address_pairs,
)
from breachlens.synth.settings import load_synth_settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def settings():
    return load_synth_settings(ROOT / "config")


@pytest.fixture(scope="module")
def pool():
    return read_pool(ROOT / "data" / "reference" / "address_pool.csv")


@pytest.fixture(scope="module")
def pop(settings, pool):
    return build_population(settings, pool)


def test_same_seed_same_population(settings, pool, pop):
    again = build_population(settings, pool)
    assert [vars(p) for p in again.people.values()] == [vars(p) for p in pop.people.values()]


def test_different_seed_differs(pool):
    other = build_population(load_synth_settings(ROOT / "config", seed=43), pool)
    a = build_population(load_synth_settings(ROOT / "config"), pool)
    assert [p.ssn for p in other.people.values()] != [p.ssn for p in a.people.values()]


def test_counts(settings, pop):
    cfg = settings.config
    base = Counter(p.state for p in pop.by_cast(BASE))
    assert dict(base) == cfg.base_people_per_state
    assert len(pop.by_cast(DEPENDENT)) == cfg.n_dependents
    assert len(pop.by_cast(STUDENT)) == cfg.n_students
    extras = Counter(p.home_sheet for p in pop.by_cast(EXTRA))
    assert dict(extras) == cfg.sheets.extras
    assert len(pop.by_cast(EXTRA_GUARDIAN)) == cfg.sheets.extras["student_roster.xlsx"]


def test_reuse_cap_and_shared_pairs_are_unrelated(settings, pop):
    check_reuse_cap(pop, settings.config.max_unrelated_households_per_address)
    pairs = shared_address_pairs(pop)
    assert pairs
    assert all(ha != hb for _, _, _, ha, hb in pairs)


def test_base_pool_share(pop):
    base = pop.by_cast(BASE)
    assert sum(1 for p in base if p.address.pool_id) / len(base) >= 0.75


def test_planted_roles(pop):
    a, b = pop.role("twin_a"), pop.role("twin_b")
    assert (a.last, a.household, a.address) == (b.last, b.household, b.address)
    assert b.dob - a.dob == timedelta(days=1) and a.ssn != b.ssn
    mover = pop.role("mover")
    assert mover.old_address is not None and mover.old_address != mover.address
    assert pop.role("ssn_area_666").ssn.startswith("666")
    assert pop.role("ssn_group_00").ssn[3:5] == "00"
    assert not ids.luhn_valid(pop.role("luhn_fail").card)
    assert pop.role("leading_zero_ssn").ssn.startswith("0")
    assert pop.role("city_typo").address.city == "SACRAMENTO"
    assert pop.role("minor_dependent").age_on(pop.as_of_date) < 18
    assert {pop.role(f"surname_{i}").last for i in range(3)} == {
        "Garcia-Lopez",
        "De La Vega",
        "Van Dyke",
    }


def test_safe_by_construction(pop):
    for p in pop.people.values():
        if p.email:
            assert p.email.rsplit("@", 1)[1] in {"example.com", "example.org", "example.net"}
        if p.phone:
            assert p.phone[5:10] == "55501"
        if p.card and p.pid != pop.roles["luhn_fail"]:
            assert p.card[:6] in {"411111", "555555"} and ids.luhn_valid(p.card)


def test_dependents_and_students_live_with_their_household(pop):
    for d in pop.by_cast(DEPENDENT):
        assert d.address == pop.people[d.subscriber].address
    for s in pop.by_cast(STUDENT):
        assert s.address == pop.people[s.guardian].address


def test_as_of_date_comes_from_pipeline_yaml(settings, pop):
    from breachlens.config import load_config

    as_of = load_config(ROOT / "config" / "pipeline.yaml").as_of_date
    assert settings.config.as_of_date == as_of == pop.as_of_date
