"""V10 evidence, provenance, confidence, and citation primitives.

Research conclusions should not invent provenance at the end. Evidence carries
its source identity from the moment it enters the Runtime, and synthesis can
only cite evidence that was actually collected.

All bundled records are synthetic teaching data, not real market or macro data.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    title: str
    publisher: str
    uri: str

    def to_dict(self) -> dict:
        return deepcopy(asdict(self))


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    claim: str
    value: float
    unit: str
    confidence: float
    source: SourceRef
    note: str = "synthetic teaching evidence"

    def __post_init__(self):
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict:
        payload = deepcopy(asdict(self))
        payload["kind"] = "evidence"
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "EvidenceRecord":
        if not isinstance(payload, dict) or payload.get("kind") != "evidence":
            raise ValueError("payload is not an evidence record")
        source = SourceRef(**payload["source"])
        return cls(
            evidence_id=payload["evidence_id"],
            claim=payload["claim"],
            value=payload["value"],
            unit=payload["unit"],
            confidence=payload["confidence"],
            source=source,
            note=payload.get("note", "synthetic teaching evidence"),
        )


class EvidenceStore:
    """Runtime-owned provenance registry for one research plan."""

    def __init__(self):
        self._records: dict[str, EvidenceRecord] = {}

    def add(self, record: EvidenceRecord) -> None:
        if not isinstance(record, EvidenceRecord):
            raise TypeError("record must be an EvidenceRecord")
        existing = self._records.get(record.evidence_id)
        if existing is not None and existing != record:
            raise ValueError(f"evidence_id collision: {record.evidence_id}")
        self._records[record.evidence_id] = record

    def get(self, evidence_id: str) -> EvidenceRecord:
        if evidence_id not in self._records:
            raise KeyError(f"Unknown evidence_id: {evidence_id}")
        return self._records[evidence_id]

    def all(self) -> list[dict]:
        return [record.to_dict() for record in self._records.values()]

    def citations(self, evidence_ids: list[str]) -> list[dict]:
        citations = []
        for evidence_id in evidence_ids:
            record = self.get(evidence_id)
            citations.append(
                {
                    "citation": f"[{record.evidence_id}]",
                    "evidence_id": record.evidence_id,
                    "title": record.source.title,
                    "publisher": record.source.publisher,
                    "uri": record.source.uri,
                    "claim": record.claim,
                }
            )
        return citations


SYNTHETIC_EVIDENCE_CATALOG = {
    "energy": EvidenceRecord(
        evidence_id="E1",
        claim="Synthetic energy component contribution is 0.4 percentage points.",
        value=0.4,
        unit="percentage_points",
        confidence=0.92,
        source=SourceRef(
            source_id="SRC-ENERGY",
            title="Teaching Energy Bulletin",
            publisher="Synthetic Data Lab",
            uri="teaching://energy-bulletin",
        ),
    ),
    "shelter": EvidenceRecord(
        evidence_id="E2",
        claim="Synthetic shelter component contribution is 0.3 percentage points.",
        value=0.3,
        unit="percentage_points",
        confidence=0.88,
        source=SourceRef(
            source_id="SRC-SHELTER",
            title="Teaching Shelter Bulletin",
            publisher="Synthetic Data Lab",
            uri="teaching://shelter-bulletin",
        ),
    ),
}


def lookup_synthetic_evidence(topic: str) -> dict:
    """Return one deterministic teaching evidence record."""
    record = SYNTHETIC_EVIDENCE_CATALOG.get(topic)
    if record is None:
        raise ValueError(f"Unknown synthetic evidence topic: {topic}")
    return record.to_dict()


def synthesize_two_evidence(evidence_a: dict, evidence_b: dict) -> dict:
    """Synthesize only from supplied evidence and preserve citation IDs."""
    first = EvidenceRecord.from_dict(evidence_a)
    second = EvidenceRecord.from_dict(evidence_b)
    if first.unit != second.unit:
        raise ValueError("Evidence units must match before synthesis")

    total = round(first.value + second.value, 4)
    confidence = min(first.confidence, second.confidence)
    evidence_ids = [first.evidence_id, second.evidence_id]
    return {
        "kind": "synthesis",
        "answer": (
            "Synthetic teaching evidence indicates a combined contribution of "
            f"{total} percentage points. [{first.evidence_id}] [{second.evidence_id}]"
        ),
        "value": total,
        "unit": first.unit,
        "confidence": confidence,
        "evidence_ids": evidence_ids,
    }
