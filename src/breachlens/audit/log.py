"""In-memory audit trail; columns follow `audit_events` in DATA_SCHEMA.md.

Callers pass values that are already masked. Persisting events (and the leak-guard scan
that must precede it) arrives in M4/M6; until then events stay in memory (ADR-044).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    run_id: str
    ts: datetime
    stage: str
    event_type: str
    item_id: str | None = None
    field: str | None = None
    code: str | None = None
    old_value_masked: str | None = None
    new_value_masked: str | None = None
    detail_json: str | None = None


@dataclass
class AuditLogger:
    """Collects audit events for one run, numbered `E000001`, `E000002`, …"""

    run_id: str
    events: list[AuditEvent] = field(default_factory=list)

    def log(
        self,
        stage: str,
        event_type: str,
        *,
        item_id: str | None = None,
        field: str | None = None,
        code: str | None = None,
        old_value_masked: str | None = None,
        new_value_masked: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=f"E{len(self.events) + 1:06d}",
            run_id=self.run_id,
            ts=datetime.now(UTC),
            stage=stage,
            event_type=event_type,
            item_id=item_id,
            field=field,
            code=code,
            old_value_masked=old_value_masked,
            new_value_masked=new_value_masked,
            detail_json=json.dumps(detail, sort_keys=True) if detail is not None else None,
        )
        self.events.append(event)
        return event
