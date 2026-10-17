import json

from breachlens.audit.log import AuditLogger


def test_events_are_numbered_per_run():
    audit = AuditLogger(run_id="R20261017-153000-ab12")
    first = audit.log("validate", "RULE_FIRED", item_id="M00001", code="NAME_MISSING")
    second = audit.log("resolve", "MERGE", item_id="P0001")
    assert (first.event_id, second.event_id) == ("E000001", "E000002")
    assert all(e.run_id == "R20261017-153000-ab12" for e in audit.events)
    assert len(audit.events) == 2


def test_detail_is_stored_as_sorted_json():
    audit = AuditLogger(run_id="R20261017-153000-ab12")
    event = audit.log("sheets", "VALUE_CHANGED", detail={"b": 1, "a": "x"})
    assert event.detail_json == '{"a": "x", "b": 1}'
    assert json.loads(event.detail_json) == {"a": "x", "b": 1}


def test_detail_defaults_to_none():
    event = AuditLogger(run_id="R20261017-153000-ab12").log("ingest", "FILE_SEEN")
    assert event.detail_json is None
    assert event.old_value_masked is None
