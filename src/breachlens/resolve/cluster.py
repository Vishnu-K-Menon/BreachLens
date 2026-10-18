"""Union-find clustering over MERGE edges with a cluster-level cannot-link guard.

Edges are applied in score order. Two clusters are never joined when their SSN keys or
their DOBs conflict (no equal or day-month-transposed pair). This keeps twins apart when a row
without SSN or DOB scores high against both (ADR-064). A refused edge is recorded as
`guard_fired = CLUSTER_CONFLICT`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from breachlens.resolve.features import f_dob


@dataclass
class Clusters:
    parent: list[int]
    ssn: list[set[str]]
    dob: list[set[date]]
    min_edge: list[float] = field(default_factory=list)

    @classmethod
    def of(cls, ssn_keys: list[str | None], dobs: list[date | None]) -> Clusters:
        n = len(ssn_keys)
        return cls(
            list(range(n)),
            [{k} if k else set() for k in ssn_keys],
            [{d} if d else set() for d in dobs],
            [1.0] * n,
        )

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def conflict(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        ssn = self.ssn[ra] and self.ssn[rb] and not (self.ssn[ra] & self.ssn[rb])
        # DOBs conflict when no pair is equal or a day-month transposition (f_dob >= 0.7)
        dob = (
            self.dob[ra]
            and self.dob[rb]
            and not any((f_dob(x, y) or 0) >= 0.7 for x in self.dob[ra] for y in self.dob[rb])
        )
        return bool(ssn or dob)

    def union(self, a: int, b: int, score: float) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True  # already joined; confidence counts spanning edges only
        if self.conflict(ra, rb):
            return False
        if ra > rb:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.ssn[ra] |= self.ssn[rb]
        self.dob[ra] |= self.dob[rb]
        self.min_edge[ra] = min(self.min_edge[ra], self.min_edge[rb], score)
        return True
